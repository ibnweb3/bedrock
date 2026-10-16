# Demo video script (2:15)

Voice: ElevenLabs, one uncut take (model eleven_v4, voice "Jarnathan", stability 0.18, similarity 0.75, style 0.65, speaker boost off).
Screen: a live recording of the product page and the running app, driven on the narration clock, no captions.
Every number spoken is on screen: the corpus figures are on the product page, the audit counts are the real result for the built-in 9-paper example.
The agent run shown is a real run on that example (fetched beforehand so the timing is fixed; the content is the model's real output).

| # | Time | Screen | Narration |
|---|---|---|---|
| 1 | 0:00 | Product page, hero | Imagine you have spent a year on a literature review, and every source on your list checks out, because your reference manager flags nothing, |
| 2 | 0:08 | The citation chain: your reference, an unflagged source, a retracted paper | but two steps back, one of those sources leans on a paper that was retracted years ago, and no tool you use was ever going to tell you, |
| 3 | 0:17 | The three corpus numbers | and this is not rare, because among the two hundred and fifty-one thousand, six hundred and forty-five articles we checked, seven thousand, one hundred and sixty-two, about two point eight percent, cite work that has since been retracted. |
| 4 | 0:31 | Back to the headline | This is Bedrock, our entry for Track One of Graph Hacks, an agent that follows every citation path from your bibliography to retracted research, built on FalkorDB. |
| 5 | 0:42 | App: "Try an example" runs the audit | So let's try it, I load a real reference list of nine papers and run the audit, |
| 6 | 0:47 | Summary counts | and in a fraction of a second, FalkorDB has walked the citation graph and sorted every paper, two retracted outright, two that cite a retracted work directly, and two that reach one through another paper. |
| 7 | 1:01 | A retracted card with reasons, then the path diagrams, then a clean card | Each finding comes with its exact citation path, the retraction date, and the recorded reasons, so you can check it yourself, and a paper with no exposure found is never called safe, only not found within two hops. |
| 8 | 1:14 | A question is typed | Now the agent, where I can ask a question in plain English, |
| 9 | 1:18 | Agent summary, then "What the agent did" | and it reads the graph with three read-only tools, then writes a summary, while our code makes sure the counts come from the audit, and that every paper it mentions was really returned by a tool, so an invented one would be flagged. |
| 10 | 1:31 | Proposed actions: tick "remove" and a replacement | The agent proposes edits, but it can never make them, so here I choose what to accept, removing the retracted paper and keeping a replacement that other papers cite alongside it, with the fit marked as unverified, |
| 11 | 1:44 | Revised list | and the result is a revised reference list and a report that contain only the changes I approved. |
| 12 | 1:50 | Product page: the backtest table and verdict | We also tried the obvious next step, predicting which papers will be retracted, and we wrote the pass mark before looking, and it failed, so Bedrock makes no predictions, only exact provenance, and we say so plainly. |
| 13 | 2:05 | Hero | Bedrock, built on FalkorDB, with the agent running on Groq, and the code written with Claude Code, a prompt for human review, never an accusation. |

Spelling note for the voice: the text sent to the voice writes it "Falkor D B" so it is pronounced clearly.

Re-making the video (from `C:\Users\IBN\Documents\Claude\demo-video-kit\bedrock`, in Git Bash): `. ./env.sh`, then `node tts.mjs` (spends ElevenLabs
credits), `node record.mjs`, `node mix.mjs`. `DRY=1 node tts.mjs` rehearses the timing for free. Needs the app on port 8780 and the product page on 8790.
