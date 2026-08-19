
These are some tests that a good design must pass.


## Infinite Context Test

In theory, the agent should have ability to process infinitely long text.

Infinite reading: read and comprehend infinite-long text, while context stays the same size.

Infinite writing: produce as much as required, while context stays the same size.

Infinite complexity: complete tasks however complicated they are, while context stays the same size.

### Fixed Context Size

We are not saying that the model should have a very small, specific size of context window (eg. 4K or 8K tokens). We mean that it does not **grow** with the task complexity.

## Computational Completeness

The agent should be Turing-complete.


## Functionalities

The model can take a stack thinking mode.

> If this is done through a recursive language model, stack is automatically achieved.
> However, we also want to ask if the model (without calling a recursive model) can implement a stack mode and read only from the top of the stack. 

For example, the model writes register 1 as the strategy in this stack. It then writes the stack as a file, storing the strategy and stack variables. The file name is stored in register 0. Now the model decides to push a new layer on top of the stack. It writes the value of register 0 to register 2, modifies register 1, writes a new file name in register 0, and stores the value of register 2 in the new file. Now, if it wants to pop the stack top, it reads the next stack top from the new file, overwrites register 0 (popping the stack top), then picks up the strategy in the new stack top to restore register 1.

To enable this strategy, the model needs to come up with this plan, and store it somewhere. 
- If it stores it in register, we need to make sure there is a type of "global special register", whose functionality does not change, and which does not change until the model explicitly sets its value; something like "global strategy". 
- If it stores it in a file, then it's safe to open that file to read the strategy at any time. But for file reads, we need to make sure this is also stacked (there should be multiple opened files and we take care of the status of opened files).

