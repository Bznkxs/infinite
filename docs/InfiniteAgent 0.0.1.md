
InfiniteAgent is a recursive agent that keeps track of a limited active context length, storing other trajectories in reliable storage while keeping a reference.

# 0.0.1

## Input

```
[System Message]
...

[Tools]
...

[Registers]
...

[Canvas]
...

[Tool response]
...

[Workspace]

```

## System Message

```
You are a helpful assistant. 

Read the user instructions from <instruction.md>.  

In addition to the user instruction, write your final response to <response-12193275.json>.

This is not necessarily the first step of model generation; the past trajectory is not included here. It is stored in <trajectory-12193275.jsonl>.

You are provided with <number> registers that will stay in the active context. Each register cannot exceed <number> chars. The first <x> registers are special and you cannot write to them. Write whatever you want to remember to the register area, as others will only be visible through reading the trajectory. 

You are provided with a canvas (a text reader). You can read any file using canvas, but you can only see a maximum of <number> chars at the same time. Use tools to open different files and navigate different parts of text.

Your workspace is also limited. You can generate at most <number> tokens. If your generation is too long, it will be truncated and saved to the trajectory. If there is an unfinished generation, register <number> will be flagged as True. In that case, check the trajectory to continue generating.

```

Content in `<>` should be substituted with actual, dynamically generated or configured value.

> See below regarding the final response. 

## Tools

#### Basic

File write access and bash command. 
* The model should be able to write a string to a file.
* The model should be able to run a bash command. The stdin and stdout results should be directed by the system to be saved in two new files every time a bash command is run. Two special registers keep the output file paths. 

#### Stack Operation (TBD)

#### Canvas Operation

> Thinking about changing this into pure terminal display; for 0.0.1 we will do this simplified version of text reader only.

`load(filename)`: Load a file in canvas. Canvas is of limited size; will only show X chars along with the file name (only the first Y chars of the file name will be shown). If the file is already tracked, switch to that file. 
- "Load" means that the system takes a snapshot of the file and shows an excerpt. Every time the file is opened (switched), the system reads from the file, so the content may be different from the previous time.
- Once a file is loaded, it is also tracked in the system. Tracked means that the system remembers the status of the reader (eg. the index of the first displayed char). There can be multiple tracked files. They form a stack. The loaded file is always at the top of the stack. If the model tries to load a tracked file, that file is removed from the stack and reinserted to the top of the stack.

`close()`: close the current file in canvas. Removes it from the top of the stack (stop tracking).

`nav(n)`: start display from the `n`-th char. (n starts from 0)

> If file `a` is not tracked, `load(a)` means start display from the 0-th char. If `nav(10)` is called when `a` is loaded, and `load(a)` is called a second time, then reload from disk and start display from the 10th char.

The canvas will be displayed as a dict:

```
{
    "path": "path/to/file",
    "last_opened_file": "path/to/second/file/in/stack" (or None),
    "length": N,
    "start": n,
    "display_length": l,
    "content": "..."
}
```

(or None if there is no opened file.)

#### Register tools

`set(value, number)`: set the `number`-th register to `value`. 

Return will be a status and an optional error message.

#### Recursive model spawn and model response

`spawn(prompt, return_schema)`

`return_schema` is always a dict. It follows anthropic's `input_schema` format for tools. Eg:

```
            {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "The unit of temperature",
                    },
                },
                "required": ["location"],
            },
```

The model's response must follow the format. The system checks the response against the format, rejecting the answer and respawning if the check fails.

This is ideally implemented in one of the following ways: 
- Option A: the system modifies the system prompt, designates a json file, and asks the model to write to that json file as a response. The model calls the normal file access / execution tool to write the file.
- Option B: the model calls a designated response tool to return the result.
	- The tool schema should be dynamically determined by `return_schema` each time.
	- Nevertheless, the system should write the response to a json file and pass the path to that file to the model.

#### Trajectory

Trajectory is stored as a .jsonl file. Every step is stored in one line. The model should not be able to write to the file; it can only read the file. Largely follow the standard practice but there should be some variations:
- I am thinking about introducing `truncate`, which is a flag that controls if the trajectory is self-contained. The file that is provided in the agent sandbox (which the model can see) should be `truncate=True`, and the record that is actually stored for us to analyze should be `truncate=False`. However, this makes things complicated. For 0.0.1, lets fix `truncate=False`.
- User message is the first step, although it is not directly provided to model (model should read from a markdown file)
- For each model response step that has tool_calls, the step should also have an "observation" field, whose value is a dict with only one key "results". Each tool call should correspond to one result in "observation.results" (whose value is a list). The result should have the following format:
	- Bash commands should have three keys "stdout", "stderr", and "file". 
		- Both stdout and stderr stores the real string; if stdout or stderr string is too large (for example, >200 char), truncate if `truncate` is True. 
		- "file" links to the corresponding output json file. 
	- For canvas operation, "content" should be the new canvas dict if `truncate=False` , and if `truncate=True` , it should be the full canvas dict (with key "content") only when the command is `load`; "content" should be the dict excluding the "content" key for other commands.
	- For register tools, the "status" should be nothing or an error message.
	- For model spawn, "content" value should be a dict with a "trajectory" key, and a "response" key. The "trajectory" value is the path to the trajectory file of the spawned model. "response" is a dict. The model response (format designated by spawn) is stored in a separate file determined by the system; include the path to that file in "response.file". If `truncate=False`, also include "response.content" and include the actual response.



## Variations

### 0.0.1-simple

In the simplest scaffold, every dynamic part of context should be seen as a register. Canvas is a special register with a large length limit. 
- Default generation length is 8192 tokens.
- `load(filename, start, register_id)` is the only file read tool. It can load any file to any register, starting from char `start` (from 0). If `start` is larger than or equal to the string length, that register gets an empty string. 
- 33 numbered registers in total, starting from 0. Canvas is register 32.
	- The registers have different max supported lengths: the first 32 registers support strings up to `max_register_length` chars, and canvas supports up to `max_canvas_length` chars. Length refers to the length of the string; if the stored object is not a string, convert to a string and calculate the length. 
	- Registers 0-1 are special: 0 stores the tool result (see below for details) and 1 is a flag set to True when previous model generation is cut off, and False otherwise.
- Write operation is done by bash.
- All bash tools and spawn tools should set a destination register. That register will store the return information, such as stdout, stderr, model response for spawn, etc. If the return information is too long (exceeds what a register can store), truncate.
	- The return information is also stored in one json file. One special register (register 0) points to the json file of the last ONE tool operation (other files are not recorded in register). For bash, that json file should contain stdout and stderr. For spawn, that return information file should be the designated result json file, not the trajectory.
	- Special registers can not be designated as the destination register of any tool.
- tool list:
	- `load(filename, start, register_id)`
		- Register 0 holds the file's total length.
	- `bash(command: string, register_id: int)`
		- Register `register_id` will store the terminal output (stdout, stderr combined as a string in order of generation; this means they are bound to the same pipe). This is the simplest version, so we do not differentiate stdout and stderr.
		- A json file that stores the full output is written; the file name is stored in Register 0.
	- `spawn(prompt: string, return_schema: dict, register_id: int)`
		- System will try to spawn a model and make it generate a json file that fits the return schema. 
		- Register 0 stores the json file name.
		- If there is an error spawning the model (i.e. there eventually is not a prepared return json file. eg. time out; network error; rate limit; file system error), the return value should be an error message.
	- `set(value: any, register_id: int)`: set a register to any value. If value is not a string, it needs to be able to convert to a string, and the resulting string should not exceed the register size; system should do this check. 
		- If it exceeds the size, return an error message, and do not change the register. This error message should directly be set to register 0; no file should be generated. Else, register 0 reports an OK message.
- Trajectory file should be accessible (read-only); no truncation.
- Modify prompt accordingly.