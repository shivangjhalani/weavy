The goal of this project currently is to build the backend for arakne. Currently I just want python scripts without API implementation (but I want to be able to create fastapi easily later).

Under arakne/ should live the source of the complete backend.

1. Audio-to-Transcript Pipeline: For now, when there is no API, I will be ingesting the audio files using the python script directly and convert it to whisper json transcript. Raw audio is designed to be retained even in the final app. The audio files in the app will have a time limit, so no need to worry about it.

2. The tech stack to be used is: FalkorDB, litellm (for llms and speech to text models (currently gemini, gemini-embeddings-001 and whisper through groq)). Also I want you to clearly mention in Memory-v5 that the nodes will store all the logs, even if they exceed the log budget, but the tool calls will be designed as such that when agent calls to get the full node details, then only the logs in budget are sent and a summary (previously generated when logs exceed budget) will be sent telling till how much time more logs are present and the summary of those cold logs as well as a new tool call introduced at the end of the summary if agent wants to get those cold logs. So no seperate DB table, it would be stored in falkorDB itself. As for sequential token registry, there will be no concurrent writes as of now, everything is sequential.

3. THERE IS NO BUDGET FOR ANYTHING RIGHT NOW, no timeouts, no toolcall budget as of now. as for the query agent, I need you to reason hard and figure out a tool call similar to complete_ingestion that is just as elegant as complete_ingestion tool call.

4. I want k to be token-budget-derived, so technically there is no k, just put enough themes in hot set that fit a configurable budget for hot themes. Now as for how to structure the themes, I want you to think hard and figure out the most simple and elegant way.

5. Theme agent has no proverance, that is intentional. As for delete, why would I need proverence if they are deleted and how would that delete proverance even be stored? Need to discuss this And as for chat-driven corrections, the proverance should just mention the chat somehow. Need to think more on this.

6. Yes prompt guidance only. I do not want to enforce it right now, will handle later if proves to be an issue. Am tryong not to prematurely engineer.
   For now let it be manual, I will deisgn a merge node tool if needed. Currently I would not ask the prompt to merge in the prompt, if it wants to it'll go off on its own to do it. Do not discuss this leave it be for now.

7. No concurrent ingestion.

8. I want embeddings updating to be lazily background job. But I want to make sure embeddings are updated on every update_node if the things that generate embeddings are changed. updated embedding would not be available to subsequent search_graph calls in the same session.

9. For now, I just wany to design for the steady state. I will see if new prompt to be designed for very first recording or prompts to be updated as graph state evolves, for now, keep it steady state and if tool calls return nothing, then agent would assume graph is empty.

10. Yes just like themes, there would be a configurable token budget, tokens for both theme and logs need to be estimated. Figure out what is the easiest way to estimate tokens (not naive math calculation, I want a robust way which is also very fast)

11. Yes all graph modification (after ingestion ends or a chat session ends, would trigger theme agent)

12. Yes I want to keep it just python backend sripts, no api for now but I should be able to easily wrap this backend behind an API.

---

YOUR GOAL: understand all that I said and I need you to create a plan to update all the requred things in Memory-v5.md very neatly in natural flow and language.
If need be, you are free to create more files in markdowns/ folder to adreess more things.

Before you write anything, there are things to discuss, lets go back and forth to figure out and complete the plan to make the documents full-proof

---

A. I agree
B. For now keep it chat:N, null, null
C. For touched_nodes, i want the action to be added to every touched node and inlcude deleted nodes as well. Make updates in the markdowns where required
D. Use tiktoken if it is fast to estimate number of tokens.
E. Yes
F. Yes
