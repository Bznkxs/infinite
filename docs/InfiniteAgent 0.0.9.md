
0.0.8 failed because of loops. Loops (livelock) means the model keeps reading and reading the same files, updating its status (registers) in a row trying to gather information more than its context, without writing anything. 

First we need to clarify the responsibilities.

## Who is responsible for the loop?

In theory, the model knows that it has a small context length and must try to keep its workset small, instead of reading a lot of text and try to write something big. This is to say, we claim that there exists a hypothetic model that works well under this scaffold 0.0.8 if it takes the best strategy of keeping its steps small at all times. This is a problem with the model's strategy. 

The problem with the scaffold is that real models do not necessarily have such strategy, and may indeed run out of its free context. Here comes the problem on the scaffold's side: the scaffold doesn't tell the model enough information about its trajectory. Judging only from the current context, the model doesn't know it is stuck, even with flags like "stall" because it doesn't exactly know what it has done. 

Let me clarify this: width is the problem with the model's strategy, since a good model doesn't require much width to do things. But the danger of loop is the problem with scaffold, since it doesn't tell the model how it is stuck.

## Summariser doesn't work well to eliminate the loop

The summariser was initially designed to eliminate the loop. It does help a bit from the previous versions, but it clearly doesn't work well. 

Either we think of a better, lossy compression to prevent loop, or we think about other strategies.

