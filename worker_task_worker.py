import asyncio
import logging
import traceback
from asyncio.exceptions import CancelledError, TimeoutError
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import aiohttp
import uvicorn
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .task import Session, Task
from .task_worker_grpc import GrpcTransport
from .typings import (
    AgentOutput,
    AgentOutputStatus,
    CancelRequest,
    CalculateOverallRequest,
    ChatHistoryItem,
    HistoryItem,
    InteractRequest,
    RewardHistoryItem,
    SampleIndex,
    SampleStatus,
    SampleStatusRequest,
    TaskOutput,
    ToolList,
    WorkerStartSampleRequest,
)


class RunningSampleData:
    index: SampleIndex
    custom_task: Optional[dict]
    session_id: int
    session: Session
    asyncio_task: asyncio.Task
    cancelling: bool

    def __init__(self,
                 index: SampleIndex,
                 session_id: int,
                 session: Session,
                 task: asyncio.Task,
                 custom_task: Optional[dict] = None):
        self.index = index
        self.custom_task = custom_task
        self.session_id = session_id
        self.session = session
        self.asyncio_task = task
        self.cancelling = False


def split_history(history: List[HistoryItem]) -> Tuple[List[ChatHistoryItem], List[RewardHistoryItem]]:
    """
    Splits the history into two parts: chat history and reward history.
    """
    chat_history = []
    reward_history = []
    for item in history:
        if isinstance(item, RewardHistoryItem):
            reward_history.append(item)
        elif hasattr(item, 'root') and isinstance(item.root, RewardHistoryItem):
            reward_history.append(item.root)
        else:
            chat_history.append(item)
    return chat_history, reward_history


def model_dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode='json')
    return obj


class TaskWorker:

    app: FastAPI

    def __init__(
        self,
        task: Task,
        controller_address: str,
        self_address: Optional[str] = None,
        heart_rate: int = 8,
        logger: logging.Logger = logging.root
    ) -> None:
        self.logger = logger

        self.session_map: Dict[int, RunningSampleData] = dict()
        self.task = task
        ToolList.model_validate(self.task.tools)

        self.controller_address = controller_address
        if self.controller_address.startswith('grpc://'):
            self.grpc_transport: Optional[GrpcTransport] = GrpcTransport(self)
            self.controller_address = self.controller_address.replace('grpc://', 'http://').rstrip('/') + '/api'
        else:
            self.grpc_transport: Optional[GrpcTransport] = None

        self.worker_id = str(uuid4())
        logger.info(f'Task worker initialized with worker_id: {self.worker_id}')

        self.self_address = self_address if not self.grpc_transport else None
        self.heart_rate = heart_rate

    async def _call_controller(self,
                               api: str,
                               data: Optional[Any] = None,
                               headers: Optional[Dict[str, str]] = None):
        if api == '/cancel_notice' and self.grpc_transport:
            await self.grpc_transport.send_cancel_notice(data['session_id'])
            return None

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.controller_address + api,
                headers=headers,
                json=data,
            ) as response:
                if response.status != 200:
                    raise HTTPException(
                        400,
                        "Error: Controller returned error"
                        + "\n"
                        + (await response.text()),
                    )
                result = await response.json()
        return result

    async def heart_beat(self):
        while True:
            try:
                if self.grpc_transport:
                    await self.grpc_transport.send_heartbeat()
                else:
                    await self._call_controller(
                        '/receive_heartbeat',
                        data={
                            'name': self.task.name,
                            'address': self.self_address,
                            'concurrency': self.task.concurrency,
                            'indices': self.task.get_indices(),
                        },
                    )
            except Exception as e:
                self.logger.error(f"Heartbeat failed: {e}")
            await asyncio.sleep(self.heart_rate)

    async def task_start_sample_wrapper(self, index: SampleIndex, session: Session, session_id: int, custom_task: Optional[dict] = None):
        try:
            if index == -1:
                result = await self.task.start_sample_custom(custom_task, session)
            else:
                result = await self.task.start_sample(index, session)
            if not result:
                raise ValueError('Task execution unexpectedly returned no result')
        except CancelledError:
            self.logger.info(f'Task execution cancelled for session {session_id}')
            self.session_map.pop(session_id, None)
            await session.controller.env_finish(TaskOutput(
                index=index,
                status=SampleStatus.CANCELLED,
                result=None,
                history=session.history,
            ))
            return
        except Exception as e:
            self.session_map.pop(session_id, None)
            self.logger.error(f'Task execution failed for session {session_id}', exc_info=e)
            error = traceback.format_exc()
            await session.controller.env_finish(TaskOutput(
                index=index,
                status=SampleStatus.TASK_ERROR,
                result=error,
                history=session.history,
            ))
            return
        self.session_map.pop(session_id, None)
        await session.controller.env_finish(TaskOutput(
            index=index,
            status=result.status,
            result=result.result,
            history=session.history,
        ))

    async def start_sample(self, parameters: WorkerStartSampleRequest):
        if parameters.session_id in self.session_map:
            raise HTTPException(status_code=400, detail="Session ID already exists")
        self.logger.debug(f'{self.session_map=}')
        if len(self.session_map) >= self.task.concurrency:
            raise HTTPException(
                status_code=406,
                detail="Sample concurrency limit reached: %d" % self.task.concurrency,
            )
        session = Session(parameters.session_id)
        self.logger.info(f'session {parameters.session_id} start sample for ' +
                         (f'index {parameters.index}' if parameters.index != -1 else f'{parameters.custom_task=}'))
        task_executor = self.task_start_sample_wrapper(
            parameters.index,
            session,
            parameters.session_id,
            parameters.custom_task
        )
        t = asyncio.get_event_loop().create_task(task_executor)
        self.session_map[parameters.session_id] = RunningSampleData(
            index=parameters.index,
            session_id=parameters.session_id,
            session=session,
            task=t,
        )

        self.logger.debug("about to pull agent")
        env_output = await session.controller.agent_pull()
        history, reward_history = split_history(env_output.history[env_output.history_ptr:])
        response_content = {
            "messages": [model_dump(i) for i in history],
            "tools": model_dump(session.tools or self.task.tools),
            "status": env_output.status,
            "finish": env_output.status != SampleStatus.RUNNING,
            "reward": reward_history[-1].reward if reward_history else 0,
            "metric": reward_history[-1].metrics if reward_history else {},
        }
        self.logger.info(f"finish start_sample {parameters.session_id=}")
        return JSONResponse(
            content=response_content,
            headers={"session_id": str(parameters.session_id)}
        )

    async def interact(self, parameters: InteractRequest):
        self.logger.info(f"interacting {parameters.session_id=}")
        running = self.session_map.get(parameters.session_id, None)
        if running is None:
            self.logger.error(f"interacting with non existing session {parameters.session_id=}")
            raise HTTPException(status_code=400, detail='No such session')
        if running.session.controller.agent_lock.locked() or running.cancelling:
            self.logger.error(f"Task Executing for {parameters.session_id=}, please do not send new request")
            raise HTTPException(
                status_code=400,
                detail="Task Executing, please do not send new request.",
            )
        self.logger.debug("awaiting agent pull in interact")
        self.logger.debug(f"interacting {parameters=}")
        agent_output = AgentOutput(
            status=AgentOutputStatus.NORMAL,
            messages=parameters.messages
        )
        env_output = await running.session.controller.agent_pull(agent_output)
        if env_output.status == SampleStatus.COMPLETED and env_output.result:
            self.logger.info(f'interaction {parameters.session_id=} completed with result: {env_output.result}')
        history, reward_history = split_history(env_output.history[env_output.history_ptr:])
        response_content = {
            "messages": [model_dump(i) for i in history],
            "tools": model_dump(self.task.tools),
            "status": env_output.status,
            "finish": env_output.status != SampleStatus.RUNNING,
            "reward": reward_history[-1].reward if reward_history else 0,
            "metric": reward_history[-1].metrics if reward_history else {},
        }
        return {
            "session_id": parameters.session_id,
            "env_out": response_content,
        }

    async def cancel(self, parameters: CancelRequest):
        return await self._cancel(parameters.session_id, with_notice=False)

    async def cancel_with_notice(self, parameters: CancelRequest):
        return await self._cancel(parameters.session_id, with_notice=True)

    async def _cancel(self, session_id: int, with_notice: bool):
        if session_id not in self.session_map:
            raise HTTPException(status_code=400, detail='No such session')

        running = self.session_map.get(session_id)
        self.logger.info(f"canceling {running}")
        running.cancelling = True
        running.session.controller.env_input = AgentOutput(status=AgentOutputStatus.CANCELLED)
        running.session.controller.env_signal.release()

        # if with notice, do not wait for task cancellation, return immediately,
        #   and send another request to notice cancellation when task is finished;
        # otherwise, block request and wait for the task to finish
        self.logger.debug("awaiting task")
        async def cancel_task():
            try:
                if self.task.full_async:
                    # safe to cancel directly
                    running.asyncio_task.cancel()
                else:
                    await asyncio.wait_for(running.asyncio_task, timeout=None)
            except (CancelledError, TimeoutError):
                pass
            self.session_map.pop(session_id, None)
            if with_notice:
                await self._call_controller('/cancel_notice', data={
                    'session_id': session_id
                }, headers={
                    'session_id': str(session_id)
                })

        if with_notice:
            asyncio.create_task(cancel_task())
        else:
            await cancel_task()

        return {
            'session_id': session_id
        }

    async def cancel_all(self):
        await self._cancel_all(with_notice=False)

    async def cancel_all_with_notice(self):
        await self._cancel_all(with_notice=True)

    async def _cancel_all(self, with_notice: bool):
        sessions = list(self.session_map.keys())
        cancelling = []
        for session_id in sessions:
            cancelling.append(self._cancel(session_id, with_notice))
        await asyncio.gather(*cancelling)

    async def worker_status(self):
        return {
            "concurrency": self.task.concurrency,
            "current": len(self.session_map),
        }

    async def sample_status(self, parameters: SampleStatusRequest):
        if parameters.session_id not in self.session_map:
            raise HTTPException(status_code=400, detail="No such session")
        running = self.session_map[parameters.session_id]
        return {
            "session_id": parameters.session_id,
            "index": running.index,
            "status": running.session.controller.get_status(),
        }

    async def get_sessions(self):
        return {sid: session.index for sid, session in self.session_map.items()}

    async def get_indices(self):
        return self.task.get_indices()

    async def calculate_overall(self, request: CalculateOverallRequest):
        return self.task.calculate_overall(request.results)

    @asynccontextmanager
    async def lifespan(self, _: FastAPI):
        if self.grpc_transport:
            await self.grpc_transport.start()
        asyncio.create_task(self.heart_beat())
        try:
            yield
        finally:
            if self.grpc_transport:
                await self.grpc_transport.release()
            self.task.release()

    def run(self, host: str, port: int):
        self.app = FastAPI(lifespan=self.lifespan)

        router = APIRouter()
        router.get("/get_indices")(self.get_indices)
        router.get("/get_sessions")(self.get_sessions)
        router.get("/worker_status")(self.worker_status)
        router.post("/sample_status")(self.sample_status)
        router.post("/start_sample")(self.start_sample)
        router.post("/interact")(self.interact)
        router.post("/cancel")(self.cancel)
        router.post("/cancel_with_notice")(self.cancel_with_notice)
        router.post("/cancel_all")(self.cancel_all)
        router.post("/cancel_all_with_notice")(self.cancel_all_with_notice)
        router.post("/calculate_overall")(self.calculate_overall)

        self.app.include_router(router, prefix='/api')
        uvicorn.run(self.app, host=host, port=port)
