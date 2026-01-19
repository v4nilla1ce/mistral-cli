from __future__ import annotations

import asyncio
import json
import logging
import uuid
from random import shuffle
from typing import Union, Tuple, Optional, TYPE_CHECKING, Any, TypedDict, Dict, List, Callable, Awaitable, TypeVar

import aiodocker
import aiohttp
from aiodocker.containers import DockerContainer
from aiodocker.exceptions import DockerError

from ._base import EnvironmentController
from ._const import *
from ._typings import StateDriver
from .state import create_state_provider

if TYPE_CHECKING:
    from aiodocker.stream import Stream
    from ._delegation import EnvironmentDelegation

logger = logging.getLogger(__name__)

T = TypeVar('T')


class SessionData(TypedDict):
    containers: Dict[str, str]
    exclusive_containers: List[str]


class DockerEnvironmentController(EnvironmentController):
    """
    This driver manages Docker containers for tasks through the Docker API.

    Important Notice:
      To enable communication between the worker and each environment,
      worker containers and environment containers must be in the same Docker network.
      This network must be a custom bridge network, not the default network.
      The name of this network must be set in the `network_name` parameter.
    """

    def __init__(self,
                 delegation: EnvironmentDelegation,
                 connection: dict,
                 network_name: str,
                 state_driver: StateDriver,
                 state_options: Optional[Dict[str, Any]] = None):
        super().__init__(delegation)
        self.task_name = delegation.get_name()
        self.valid_subtypes = delegation.get_subtypes()

        self._client = None
        self._client_connection_params = connection
        self.network_name = network_name

        if state_options is None:
            state_options = {}
        self.state = create_state_provider(
            driver=state_driver,
            prefix=f'agentrl:{self.task_name}:{self.network_name}',
            **state_options
        )

        self._shells: Dict[str, Stream] = {}
        self._retryable_docker_statuses = {500, 502, 503, 504, 900}

    async def _get_client(self) -> aiodocker.Docker:
        if self._client is None or getattr(self._client.session, 'closed', False):
            if self._client is not None:
                await self._client.close()
            client_params = dict(self._client_connection_params)
            self._client = aiodocker.Docker(**client_params)
        return self._client

    async def _reset_client(self):
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                logger.warning('Error closing docker client during reset', exc_info=True)
            self._client = None
        for stream in self._shells.values():
            try:
                await stream.close()
            except Exception:
                pass
        self._shells.clear()

    async def _docker_call(self,
                           operation: Callable[[aiodocker.Docker], Awaitable[T]],
                           description: str,
                           retry: bool = True) -> T:
        attempt = 0
        max_attempts = 2 if retry else 1
        while True:
            client = await self._get_client()
            try:
                return await operation(client)
            except DockerError as exc:
                should_retry = exc.status in self._retryable_docker_statuses and attempt < max_attempts - 1
                if not should_retry:
                    raise
                attempt += 1
                logger.warning('Docker %s failed with status %s, reconnecting (attempt %s/%s)',
                               description, exc.status, attempt + 1, max_attempts)
                await self._reset_client()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt >= max_attempts - 1:
                    raise
                attempt += 1
                logger.warning('Docker %s transport error %s, reconnecting (attempt %s/%s)',
                               description, exc, attempt + 1, max_attempts)
                await self._reset_client()

    async def _load_container(self, container_id: str) -> DockerContainer:
        async def _fetch(client: aiodocker.Docker) -> DockerContainer:
            container = client.containers.container(container_id)
            await container.show()
            return container

        return await self._docker_call(_fetch, f'load container {container_id}')

    async def start_session(self, subtypes: Union[List[str], str], immutable: bool = True, **kwargs) -> Tuple[str, Dict[str, str], Dict[str, str]]:
        subtypes = subtypes if isinstance(subtypes, list) else [subtypes]
        for subtype in subtypes:
            assert subtype in self.valid_subtypes, f'invalid subtype {subtype} for task {self.task_name}'

        session_id = await self.state.generate_session_id()
        containers_allocated: Dict[str, DockerContainer] = {}
        containers_allocated_exclusive: Dict[str, DockerContainer] = {}
        non_exclusive_subtypes = []

        for subtype in subtypes:
            usage_limit = self.delegation.get_reuse_limit(subtype)
            if usage_limit == 1 or (usage_limit != 0 and not immutable):
                # exclusive allocation, no need to lock
                container = await self.create_container(subtype, exclusive=True, **kwargs)
                await self.state.allocate_container(container.id, session_id)
                containers_allocated[subtype] = container
                containers_allocated_exclusive[subtype] = container
            else:
                non_exclusive_subtypes.append(subtype)

        shared_candidates: Dict[str, List[DockerContainer]] = {}
        if len(non_exclusive_subtypes) > 0:
            shared_candidates = await self._identify_containers(non_exclusive_subtypes)

        for subtype in non_exclusive_subtypes:
            existing_containers = shared_candidates.get(subtype, [])
            shuffle(existing_containers)

            concurrency_limit = self.delegation.get_concurrency_limit(subtype)
            usage_limit = self.delegation.get_reuse_limit(subtype)

            while True:
                selected_container: Optional[DockerContainer] = None

                async with self.state.with_lock(f'allocation:{subtype}', session_id):
                    for container in existing_containers:
                        if 0 < usage_limit <= await self.state.container_total_uses(container.id):
                            continue
                        if 0 < concurrency_limit <= await self.state.container_current_uses(container.id):
                            continue
                        selected_container = container
                        break

                    if selected_container is not None:
                        containers_allocated[subtype] = selected_container
                        await self.state.allocate_container(selected_container.id, session_id)

                if selected_container is not None:
                    break

                new_container = await self.create_container(subtype, exclusive=False, **kwargs)
                existing_containers.append(new_container)

        if self.delegation.has_homepage():
            # create dedicated homepage container for the session
            homepage_subtype = self.delegation.get_homepage_subtype()
            homepage_envs = self.delegation.get_homepage_envs({
                subtype: await self.get_container_url(containers_allocated, subtype)
                for subtype in containers_allocated.keys()
            })
            homepage_container = await self.create_container(homepage_subtype, homepage_envs, exclusive=True, **kwargs)
            await self.state.allocate_container(homepage_container.id, session_id)
            containers_allocated[homepage_subtype] = homepage_container
            containers_allocated_exclusive[homepage_subtype] = homepage_container

        # save allocated container ids to the session
        await self.state.store_session(session_id, SessionData(
            containers={
                subtype: container.id
                for subtype, container in containers_allocated.items()
            },
            exclusive_containers=[
                container.id
                for subtype, container in containers_allocated_exclusive.items()
            ]
        ))

        # log allocations
        for subtype, container in containers_allocated.items():
            logger.info(f'Allocated {subtype} container {container.id} to session {session_id}')

        # release the lock, while wait for containers to be healthy
        logger.info('Waiting for containers to be healthy')
        await self._wait_for_health(*containers_allocated.values())

        # return session_id, container ids and environment urls
        return session_id, {
            subtype: container.id
            for subtype, container in containers_allocated.items()
        }, {
            subtype: await self.get_container_url(containers_allocated, subtype)
            for subtype in containers_allocated.keys()
        }

    async def renew_session(self, session_id: str):
        await self.state.renew_session(session_id)
        session: Optional[SessionData] = await self.state.get_session(session_id)
        if session:
            for container in session.get('containers', {}).values():
                await self.state.renew_container(container, session_id)

    async def end_session(self, session_id: str):
        session: Optional[SessionData] = await self.state.get_session(session_id)
        if session:
            exclusive_containers = list(session.get('exclusive_containers', []) or [])
            exclusive_container_ids = set(exclusive_containers)

            shared_containers = [
                (subtype, container_id)
                for subtype, container_id in session.get('containers', {}).items()
                if container_id not in exclusive_container_ids
            ]

            for subtype, container_id in shared_containers:
                async with self.state.with_lock(f'allocation:{subtype}', session_id):
                    await self.state.release_container(container_id, session_id)
                    logger.info(f'Released container {container_id}')

            for container_id in exclusive_containers:
                await self.delete_container(container_id)

        await self.state.delete_session(session_id)

    async def execute_command(self, environment_id: str, command: Union[str, List[str]], timeout: int = 30) -> Tuple[int, bytes, bytes]:
        exec_ = await self._docker_call(
            lambda client: client.containers.container(environment_id).exec(command),
            f'exec {environment_id}',
            retry=False
        )

        stdout_data = bytearray()
        stderr_data = bytearray()
        async with exec_.start(timeout=timeout, detach=False) as stream:
            while True:
                message = await stream.read_out()
                if message is None:
                    break
                if message.stream == 1:
                    stdout_data.extend(message.data)
                elif message.stream == 2:
                    stderr_data.extend(message.data)

        exit_code = (await exec_.inspect()).get('ExitCode', 0)
        return exit_code, bytes(stdout_data), bytes(stderr_data)

    async def create_shell(self, environment_id: str, shell: str = '/bin/bash --login'):
        exec_ = await self._docker_call(
            lambda client: client.containers.container(environment_id).exec(shell, stdin=True, tty=True),
            f'shell exec {environment_id}',
            retry=False
        )
        stream = exec_.start(detach=False)
        self._shells[environment_id] = stream
        await stream._init()

        # consume first prompt
        async def read_until_prompt():
            while True:
                message = await stream.read_out()
                if message is None:
                    break
                if SHELL_PROMPT_RE.search(message.data):
                    break
        await asyncio.wait_for(read_until_prompt(), 5)

    async def execute_shell(self, environment_id: str, command: str, timeout: int = 30) -> bytes:
        if environment_id not in self._shells:
            await self.create_shell(environment_id)
        stream = self._shells[environment_id]

        await stream.write_in(command.encode('utf-8') + b'\n')

        async def read_until_prompt():
            data = bytearray()
            ignored_first_line = False
            while True:
                message = await stream.read_out()
                if message is None:
                    break
                if ignored_first_line:
                    data.extend(message.data)
                else:
                    ignored_first_line = True
                if SHELL_PROMPT_RE.search(message.data):
                    break
            return bytes(data)

        return await asyncio.wait_for(read_until_prompt(), timeout)

    async def get_env_variables(self, environment_id: str) -> Dict[str, str]:
        container = await self._load_container(environment_id)

        if not container._container:
            return {}
        if not container._container.get('Config', {}).get('Env'):
            return {}

        env_vars = {}
        for env in container._container['Config']['Env']:
            key, value = env.split('=', 1)
            env_vars[key] = value

        return env_vars

    async def background_task(self):
        while True:
            try:
                if await self.state.acquire_lock('background', timeout=120):
                    try:
                        await self._clean_containers()
                    except Exception:
                        logger.warning('Error while cleaning containers', exc_info=True)
                    await self.state.release_lock('background')
            except Exception:
                logger.warning('Error in background task', exc_info=True)
            await asyncio.sleep(10)

    async def _identify_containers(self, subtypes: Optional[List[str]] = None) -> Dict[str, List[DockerContainer]]:
        return {
            subtype: await self._docker_call(
                lambda client: client.containers.list(filters=json.dumps({
                    'label': [
                        f'{LABEL_MANAGED_BY}={LABEL_MANAGED_BY_VALUE}',
                        f'{LABEL_TASK_NAME}={self.task_name}',
                        f'{LABEL_SUBTYPE_NAME}={subtype}',
                        f'{LABEL_EXCLUSIVE}={str(False).lower()}'
                    ],
                    'status': ['running'],
                    'health': ['starting', 'healthy', 'none'],
                    'network': [self.network_name]
                })),
                f'list containers for {subtype}'
            )
            for subtype in subtypes or self.valid_subtypes
        }

    async def _wait_for_health(self, *containers: Union[DockerContainer, str]):
        container_ids = [c.id if isinstance(c, DockerContainer) else c for c in containers]
        while True:
            not_started_containers = await self._docker_call(
                lambda client: client.containers.list(filters=json.dumps({
                    'id': container_ids,
                    'status': ['created'],
                    'network': [self.network_name]
                })),
                'list created containers'
            )
            if len(not_started_containers) > 0:
                await asyncio.sleep(1)
                continue

            unhealthy_containers = await self._docker_call(
                lambda client: client.containers.list(filters=json.dumps({
                    'id': container_ids,
                    'health': ['starting', 'unhealthy'],
                    'network': [self.network_name]
                })),
                'list unhealthy containers'
            )
            if len(unhealthy_containers) == 0:
                break
            await asyncio.sleep(1)

    async def create_container(self, subtype: str, extra_envs: Dict[str, str] = None, exclusive: Optional[bool] = None, **kwargs) -> DockerContainer:

        if not extra_envs:
            extra_envs = {}

        if exclusive is None:
            exclusive = self.delegation.get_reuse_limit(subtype) == 1

        # generate container name
        container_name = f'{subtype.replace("_", "-").lower()}-{uuid.uuid4().hex[:8]}'

        attrs = {
            'Name': container_name,
            'Env': {},
            'Labels': {
                LABEL_MANAGED_BY: LABEL_MANAGED_BY_VALUE,
                LABEL_TASK_NAME: self.task_name,
                LABEL_SUBTYPE_NAME: subtype,
                LABEL_EXCLUSIVE: str(exclusive).lower(),
            },
            'HostConfig': {
                'AutoRemove': True,
                'Init': True,
                'NetworkMode': self.network_name
            }
        }

        # delegate container configuration
        attrs = await self.delegation.create_docker_container(attrs, subtype, **kwargs)
        if 'Image' not in attrs:
            attrs['Image'] = self.delegation.get_container_images()[subtype]

        # override extra envs
        for k, v in extra_envs.items():
            attrs['Env'][k] = v

        # transform attrs to required format
        attrs['Env'] = [
            f'{k}={v}'
            for k, v in attrs['Env'].items()
        ]
        if 'Name' in attrs:
            container_name = attrs['Name']
            del attrs['Name']

        # create container
        async def _create(client: aiodocker.Docker) -> DockerContainer:
            return await client.containers.create(attrs, name=container_name)

        try:
            container = await self._docker_call(_create, f'create container {container_name}', retry=False)
        except DockerError as e:
            if e.status == 404:
                logger.warning(f'Image {attrs["Image"]} is not found, pulling it to try again...')
                try:
                    await asyncio.wait_for(
                        self._docker_call(
                            lambda client: client.images.pull(attrs['Image']),
                            f'pull image {attrs["Image"]}'
                        ),
                        120
                    )
                except asyncio.TimeoutError:
                    logger.error(f'Timeout while pulling image {attrs["Image"]}')
                    raise e
                container = await self._docker_call(_create, f'create container {container_name}', retry=False)
            else:
                raise

        logger.debug(f'Created container {container_name} with {attrs=}')

        # start container and update info
        await container.start()
        await container.show()

        # call post-create hook in new coroutine to prevent blocking lock
        asyncio.create_task(self.post_create_container(subtype, container))

        return container

    async def post_create_container(self, subtype: str, container: DockerContainer):
        if 'post_create_docker_container' not in self.delegation.__class__.__dict__:
            return  # not implemented by the delegation

        await self._wait_for_health(container)
        await self.delegation.post_create_docker_container(
            subtype,
            container.id,
            await self.get_container_url(container, subtype)
        )

    async def delete_container(self, container: Union[DockerContainer, str]):
        if isinstance(container, DockerContainer):
            container_obj = container
            if not getattr(container_obj, '_container', None):
                try:
                    await container_obj.show()
                except Exception:
                    pass
        else:
            try:
                container_obj = await self._load_container(container)
            except DockerError:
                container_obj = None

        container_id = container_obj.id if isinstance(container_obj, DockerContainer) else str(container)

        stream = self._shells.pop(container_id, None)
        if stream:
            try:
                await stream.close()
            except Exception:
                pass

        labels = {}
        if container_obj and getattr(container_obj, '_container', None):
            labels = container_obj._container.get('Labels', {}) or {}

        depends_on = labels.get(LABEL_DEPENDS_ON)
        if depends_on:
            for dep in depends_on.split(','):
                dep = dep.strip()
                if dep:
                    await self.delete_container(dep)

        async def _delete(client: aiodocker.Docker):
            target = client.containers.container(container_id)
            await target.delete(v=True, force=True)

        try:
            await self._docker_call(_delete, f'delete container {container_id}', retry=False)
        except DockerError:
            pass
        except aiohttp.ClientError:
            pass

        await self.state.remove_container(container_id)
        logger.info(f'Deleted container {container_id}')

    async def _clean_containers(self):
        # remove unused exclusive containers
        containers = await self._docker_call(
            lambda client: client.containers.list(filters=json.dumps({
                'label': [
                    f'{LABEL_MANAGED_BY}={LABEL_MANAGED_BY_VALUE}',
                    f'{LABEL_TASK_NAME}={self.task_name}',
                    f'{LABEL_EXCLUSIVE}={str(True).lower()}'
                ],
                'network': [self.network_name]
            })),
            'list exclusive containers'
        )
        for container in containers:
            if not await self.state.container_is_allocated(container.id):
                await self.delete_container(container)

        # remove not used unhealthy non-exclusive containers
        # no need to lock
        containers = await self._docker_call(
            lambda client: client.containers.list(filters=json.dumps({
                'label': [
                    f'{LABEL_MANAGED_BY}={LABEL_MANAGED_BY_VALUE}',
                    f'{LABEL_TASK_NAME}={self.task_name}',
                    f'{LABEL_EXCLUSIVE}={str(False).lower()}'
                ],
                'health': ['unhealthy'],
                'network': [self.network_name]
            })),
            'list unhealthy shared containers'
        )
        for container in containers:
            if await self.state.container_is_allocated(container.id):
                continue
            await self.delete_container(container)

        # remove containers that have reached their reuse limit and is not currently allocated
        for subtype, containers in (await self._identify_containers()).items():
            usage_limit = self.delegation.get_reuse_limit(subtype)
            if usage_limit == 0:
                continue
            for container in containers:
                if await self.state.container_is_allocated(container.id):
                    continue
                if await self.state.container_total_uses(container.id) < usage_limit:
                    continue
                await self.delete_container(container)

    async def get_container_url(self, containers: Union[Dict[str, Union[DockerContainer, str]], DockerContainer, str], subtype: str) -> str:
        if isinstance(containers, DockerContainer):
            # if input is a single container instance, get name / ip from it;
            container = containers
        elif isinstance(containers, dict):
            # if input is a dict, get the container of the given subtype;
            container = containers[subtype]
        else:
            container = containers
        if isinstance(container, str):
            container = await self._load_container(container)

        ip = container['NetworkSettings']['Networks'][self.network_name]['IPAddress']
        port = self.delegation.get_service_port(subtype)
        if not port:
            return ip
        if port == 80:
            return f'http://{ip}'
        return f'http://{ip}:{port}'
