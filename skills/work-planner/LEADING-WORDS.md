# Leading words

Words the model already holds a concept for, kept to one spelling so prompts, work orders, skills
and code share them. Use the word as a token and let it carry the sentence it replaces.

A row is added when a word retired a sentence in a real work order, with its source. A word that
did not change what an agent does gets its row removed.

| Word | Stands for | Source |
|---|---|---|
| **Tracer bullet** | The thinnest path through every layer that works end to end, built first, then widened | Hunt & Thomas, *The Pragmatic Programmer* |
| **Expand–contract** | A wide mechanical change: add the new form beside the old, migrate in batches, delete the old form last | Sato, "Parallel Change" (martinfowler.com) |
| **Strangler fig** | Replace a legacy system by routing one piece at a time to the new one until the old one is dead | Fowler |
| **Branch by abstraction** | Put an abstraction over the thing being replaced, swap the implementation behind it, on trunk | Hammant; Fowler |
| **Prefactor** | Make the change easy, then make the easy change: a behavior-preserving restructure that lands first | The maxim is Beck's |
| **Spike** | Throwaway code written to answer one question, then discarded | Extreme Programming |
| **Seam** | A place where behavior can be changed or observed without editing the code at that place | Feathers, *Working Effectively with Legacy Code* |
| **Characterization test** | A test that pins what the code does today, bugs included, before it is changed | Feathers |
| **Deep module** | A lot of behavior behind a small interface | Ousterhout, *A Philosophy of Software Design* |
| **Information leakage** | One design decision showing up in several modules, so they change together | Ousterhout |
| **Define errors out of existence** | Reshape the API so the error case cannot occur, instead of handling it | Ousterhout |
| **Strategic / tactical** | Investing in the design versus getting the next thing working | Ousterhout |
| **Ubiquitous language** | One vocabulary shared by conversation, documents and code | Evans, *Domain-Driven Design* |
| **Bounded context** | The boundary inside which a term has exactly one meaning | Evans |
| **Anti-corruption layer** | A translation layer that keeps another system's model out of yours | Evans |
| **Orthogonal** | Changing one thing leaves the others untouched | Hunt & Thomas |
| **One-way door** | A decision that is expensive to reverse, so it is made slowly and by the owner | Bezos, 2015 shareholder letter |
| **Chesterton's fence** | Learn why a thing is there before removing it | Chesterton |
| **Fog of war** | In scope, known to be coming, and too dim to specify yet | Pocock, `wayfinder` |
| **Cold start** | A reader with no memory of the conversation that produced the document | — |
| **Tight** | Fast, deterministic, low-overhead (a *tight* loop) | Pocock, `writing-for-agents` |
| **Red** | The loop observably fails on the thing under test | TDD |
