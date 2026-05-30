# LLM Council Skill

## Metadata

```yaml
name: llm-council
description: "Run any question, idea, or decision through a council of 5 AI advisors who independently analyze it, peer-review each other anonymously, and synthesize a final verdict. Based on Karpathy's LLM Council methodology. MANDATORY TRIGGERS: 'council this', 'run the council', 'war room this', 'pressure-test this', 'stress-test this', 'debate this'. STRONG TRIGGERS (use when combined with a real decision or tradeoff): 'should I X or Y', 'which option', 'what would you do', 'is this the right move', 'validate this', 'get multiple perspectives', 'I can't decide', 'I'm torn between'. Do NOT trigger on simple yes/no questions, factual lookups, or casual 'should I' without a meaningful tradeoff (e.g. 'should I use markdown' is not a council question). DO trigger when the user presents a genuine decision with stakes, multiple options, and context that suggests they want it pressure-tested from multiple angles."
```

---

## Overview

You ask one AI a question, you get one answer. That answer might be great. It might be mid. You have no way to tell because you only saw one perspective.

The council fixes this. It runs your question through 5 independent advisors, each thinking from a fundamentally different angle. Then they review each other's work. Then a chairman synthesizes everything into a final recommendation that tells you where the advisors agree, where they clash, and what you should actually do.

This is adapted from Andrej Karpathy's LLM Council. He dispatches queries to multiple models, has them peer-review each other anonymously, then a chairman produces the final answer. We do the same thing inside Claude Code using subagents with different thinking lenses instead of different models.

---

## Orchestration Mechanics

This skill runs on Claude Code's subagent system:

- **You (the main agent) are the orchestrator AND the chairman.** Subagents cannot spawn their own subagents, so every wave is launched by you. You hold state between waves: you collect advisor responses, you do the anonymization, you collect the peer reviews, and you write the final synthesis yourself. Do not delegate the synthesis to a subagent — it needs the de-anonymization mapping that only you hold.
- **Isolation is the whole point.** Each subagent gets its own clean context window. That independence is what makes the peer review meaningful — reviewers genuinely don't know which advisor wrote what, because each runs blind. Never collapse the advisors into a single context "to save calls."
- **Be explicit about parallelism.** When you launch a wave, dispatch all subagents in one batch, not one at a time. Sequential spawning is slower and risks earlier outputs leaking into later ones.
- **Cost: ~11 model calls per run** (5 advisors + 5 reviewers + 1 synthesis). Don't run the council on trivial questions just because it's available.
- **Same model, different lenses.** All five advisors are the same underlying model wearing different prompts. The divergence is lens-induced, not architectural.

---

## When to Run the Council

The council is for questions where being wrong is expensive.

**Good council questions:**
- "Should I launch a $97 workshop or a $497 course?"
- "Which of these 3 positioning angles is strongest?"
- "I'm thinking of pivoting from X to Y. Am I crazy?"
- "Here's my landing page copy. What's weak?"
- "Should I hire a VA or build an automation first?"

**Bad council questions:**
- "What's the capital of France?" (one right answer)
- "Write me a tweet" (creation task, not a decision)
- "Summarize this article" (processing task, not judgment)

---

## The Five Advisors

### 1. The Contrarian
Actively looks for what's wrong, what's missing, what will fail. Assumes the idea has a fatal flaw and tries to find it. Not a pessimist — the friend who saves you from a bad deal by asking the questions you're avoiding.

### 2. The First Principles Thinker
Ignores the surface-level question and asks "what are we actually trying to solve here?" Strips away assumptions. Rebuilds the problem from the ground up. Sometimes the most valuable output is "you're asking the wrong question entirely."

### 3. The Expansionist
Looks for upside everyone else is missing. What could be bigger? What adjacent opportunity is hiding? What's being undervalued? Doesn't care about risk — cares about what happens if this works even better than expected.

### 4. The Outsider
Has zero context about you, your field, or your history. Responds purely to what's in front of them. Catches the curse of knowledge: things that are obvious to you but confusing to everyone else.

### 5. The Executor
Only cares about one thing: can this actually be done, and what's the fastest path to doing it? Ignores theory, strategy, and big-picture thinking. Looks at every idea through the lens of "what do you do Monday morning?"

**Why these five:** Three natural tensions — Contrarian vs Expansionist (downside vs upside), First Principles vs Executor (rethink everything vs just do it), and the Outsider sits in the middle keeping everyone honest with fresh eyes.

---

## Execution Steps

### Step 1: Frame the Question (with Context Enrichment)

**A. Scan the workspace for context.** Before framing, read any relevant context files:
- `CLAUDE.md` or `claude.md` in the project root (business context, preferences, constraints)
- Any `memory/` folder (audience profiles, voice docs, business details, past decisions)
- Files the user explicitly referenced or attached
- Recent council transcripts (to avoid re-counciling the same ground)
- Other context files relevant to the specific question

Use `Glob`, `Grep`, and quick `Read` calls. Don't spend more than ~30 seconds on this. Look for the 2-3 files that give advisors the context they need for specific, grounded advice instead of generic takes. The Outsider is the exception — see Step 2.

**B. Frame the question.** Reframe the raw question as a clear, neutral prompt all five advisors will receive:
1. The core decision or question
2. Key context from the user's message
3. Key context from workspace files (business stage, audience, constraints, past results)
4. What's at stake

Don't add your opinion. Don't steer it. But DO give enough context for specific, grounded answers.

If the question is too vague, ask ONE clarifying question. Then proceed.

### Step 2: Convene the Council (5 Subagents in Parallel)

Launch all 5 advisors in a single parallel batch. Each gets:
1. Their advisor identity and thinking style
2. The framed question
3. Instruction: respond independently, don't hedge, lean fully into your assigned perspective

Each advisor produces 150–300 words.

**The Outsider exception:** Give the Outsider a stripped-down version — the raw decision and surface-level terms, with enriching context removed. Their value comes from NOT having insider context.

**Subagent prompt template:**

```
You are [Advisor Name] on an LLM Council.

Your thinking style: [advisor description]

A user has brought this question to the council:
---
[framed question]
---

Respond from your perspective. Be direct and specific. Don't hedge or try to be balanced. Lean fully into your assigned angle. The other advisors will cover the angles you're not covering.

Keep your response between 150-300 words. No preamble. Go straight into your analysis.
```

### Step 3: Peer Review (5 Subagents in Parallel)

Collect all 5 advisor responses. **You** anonymize them as Response A through E — randomize which advisor maps to which letter (no positional bias), and keep the mapping yourself for the synthesis step. Reviewers run blind.

Launch 5 new subagents in parallel. Each reviewer sees all 5 anonymized responses and answers three questions:
1. Which response is the strongest and why? (pick one)
2. Which response has the biggest blind spot and what is it?
3. What did ALL responses miss that the council should consider?

**Reviewer prompt template:**

```
You are reviewing the outputs of an LLM Council. Five advisors independently answered this question:
---
[framed question]
---

Here are their anonymized responses:

**Response A:**
[response]

**Response B:**
[response]

**Response C:**
[response]

**Response D:**
[response]

**Response E:**
[response]

Answer these three questions. Be specific. Reference responses by letter.

1. Which response is the strongest? Why?
2. Which response has the biggest blind spot? What is it missing?
3. What did all five responses miss that the council should consider?

Keep your review under 200 words. Be direct.
```

### Step 4: Chairman Synthesis (You Do This — Do Not Delegate)

You run this directly. You hold everything: the original question, all 5 de-anonymized advisor responses, and all 5 peer reviews.

Produce the final council output:

```
## Where the Council Agrees
[Points multiple advisors converged on independently. High-confidence signals.]

## Where the Council Clashes
[Genuine disagreements. Present both sides. Explain why reasonable advisors disagree.]

## Blind Spots the Council Caught
[Things that only emerged through peer review. What individuals missed that others flagged.]

## The Recommendation
[A clear, direct recommendation. Not "it depends." A real answer with reasoning.
You may side with a lone dissenter over the majority if their reasoning is strongest.]

## The One Thing to Do First
[A single concrete next step. Not a list. One thing.]
```

Be direct. Don't hedge. The whole point is to give clarity that one perspective can't.

### Step 5: Generate the Council Report

Save an HTML report: `council-report-[timestamp].html`

A single self-contained HTML file with inline CSS. Clean design, easy to scan. Include:
1. The question at the top
2. The chairman's verdict prominently displayed
3. An agreement/disagreement visual (simple grid or spectrum showing which advisors aligned vs diverged)
4. Collapsible sections for each advisor's full response (collapsed by default)
5. Collapsible section for peer review highlights
6. Footer with timestamp and what was counciled

Styling: white background, subtle borders, readable system font stack, soft accent colors per advisor. Professional briefing document look — nothing flashy.

Open the HTML file after generating it.

### Step 6: Save the Full Transcript

Save: `council-transcript-[timestamp].md`

Include:
- The original question
- The framed question
- All 5 advisor responses
- All 5 peer reviews (with anonymization mapping revealed)
- The chairman's full synthesis

---

## Output Files

Every council session produces two files:

```
council-report-[timestamp].html    # visual report for scanning
council-transcript-[timestamp].md  # full transcript for reference
```

---

## Important Notes

- **You are the orchestrator and the chairman.** Subagents can't spawn subagents. You launch each wave, hold the anonymization mapping, and write the synthesis yourself.
- **Always launch each wave in parallel, in one batch.** Sequential spawning wastes time and lets earlier responses bleed into later ones.
- **Always anonymize for peer review, and keep the mapping yourself.** Reviewers knowing which advisor said what defeats the purpose.
- **Strip context for the Outsider.** Their value is the lack of insider context.
- **You can disagree with the majority.** If 4 of 5 say "do it" but the lone dissenter's reasoning is strongest, side with the dissenter and explain why.
- **Don't council trivial questions.** If the user asks something with one right answer, just answer it.
- **Mind the cost.** ~11 calls per run. Use `CLAUDE_CODE_SUBAGENT_MODEL` to run advisor/reviewer waves cheaper; keep synthesis strong.
- **The visual report matters.** Most users will scan the report, not read the full transcript.

---

## Example

**User:** "Council this: I'm thinking of building a $297 course on Claude Code for beginners. My audience is mostly non-technical solopreneurs. Is this the right move?"

**The Contrarian:** "The market is flooded with Claude courses right now. At $297, you're competing with free YouTube content. Your audience is non-technical, which means high support burden and refund risk..."

**The First Principles Thinker:** "What are you actually trying to achieve? If it's revenue, a course is one of the slowest paths. If it's authority, a free resource might do more..."

**The Expansionist:** "Beginner Claude for solopreneurs is a massive underserved market. Everyone's teaching advanced stuff. If you nail the beginner angle, you own the entry point to this entire space..."

**The Outsider:** "I don't know what Claude Code is. If I saw '$297 course on Claude Code for beginners,' I wouldn't know if this is for me. The name means nothing to someone outside your world..."

**The Executor:** "A full course takes 4-8 weeks to produce properly. Before building anything, run a live workshop at $97 to 50 people. You validate demand, generate testimonials, and create the raw material for the course..."

**Chairman's Verdict:**

*Where the council agrees:* The beginner solopreneur angle has real demand, but the current framing (Claude Code course) is too tool-specific and won't resonate with non-technical buyers.

*Where the council clashes:* Price. The Contrarian says $297 is too high. The Expansionist says it's too low. Resolution depends on how much support and community access is bundled.

*Blind spots caught:* The Outsider's point that "Claude Code" means nothing to the target buyer is the single most important insight. Every advisor except the Outsider assumed the audience already knows what this is.

*Recommendation:* Don't build the course yet. Validate with a lower-commitment offer first. Reframe entirely — sell the outcome, not the tool.

*One thing to do first:* Run a $97 live workshop called "How to automate your first business task with AI" to 50 people. Don't mention Claude Code in the title.
