from agentsdk.llm import _parse_xml_tool_calls

# Test 1: basic XML tool call with Python code (braces in string values)
sample = '<function/run_python{"code": "def fib(n):\\n    dp = [0]*(n+1)\\n    dp[1]=1\\n    for i in range(2,n+1):\\n        dp[i]=dp[i-1]+dp[i-2]\\n    return dp[n]\\n\\nprint(fib(10))"}></function>'
calls = _parse_xml_tool_calls(sample)
assert len(calls) == 1, f"Expected 1 call, got {len(calls)}"
assert calls[0].name == "run_python"
assert "fib" in calls[0].arguments["code"]
print("Test 1 PASSED — run_python parsed:", calls[0].arguments["code"][:60])

# Test 2: write_file tool call
sample2 = '<function/write_file{"path": "/tmp/solution.py", "content": "print(42)"}></function>'
calls2 = _parse_xml_tool_calls(sample2)
assert len(calls2) == 1
assert calls2[0].name == "write_file"
assert calls2[0].arguments["path"] == "/tmp/solution.py"
print("Test 2 PASSED — write_file parsed:", calls2[0].arguments)

# Test 3: multiple tool calls in one content string
sample3 = 'Some text <function/read_file{"path": "a.py"}></function> and <function/run_python{"code": "1+1"}></function>'
calls3 = _parse_xml_tool_calls(sample3)
assert len(calls3) == 2
print("Test 3 PASSED — 2 tool calls:", [c.name for c in calls3])

# Test 4: no tool calls
calls4 = _parse_xml_tool_calls("Hello, here is the answer: 42")
assert len(calls4) == 0
print("Test 4 PASSED — no calls in plain text")

print("\nAll parser tests passed.")
