
path = r"d:\Projects\mistral-ai\mistral-cli\benchmarks\AgentBench\extra\worker-entrypoint.sh"
content = b'#!/bin/bash\n\nIP=$(hostname -i)\n\nexec python -m agentrl.worker --self "http://${IP}:5021/api" "$@"\n'

with open(path, "wb") as f:
    f.write(content)
print(f"Fixed {path} with LF line endings.")
