# RAG Evaluation Report
- Total queries: **114**
- Threshold mode: **strict**

## Metrics
- Recall@1: **0.544**
- Recall@3: **0.737**
- Recall@8: **0.825**
- MRR@1: **0.544**
- MRR@3: **0.632**
- MRR@8: **0.651**

## Sample Hits (first 10)
- “what is the purpose of Relativity AI for juniors?” → BND–WHAT-IT-DOES-PRINCIPLE: (rank 3)
- “how does the junior ladder work from graduate to junior?” → BND–FUNCTION–PURPOSE (rank 1)
- “how does the plan–personalize–execute principle work?” → BND–WHAT-IT-DOES-PRINCIPLE: (rank 1)
- “how do you personalize learning using my preferences?” → BND–WHAT-IT-DOES-PRINCIPLE: (rank 1)
- “how do you help me think outside the box while learning?” → BND–WHAT-IT-DOES–VALUE-PREP: (rank 1)
- “do you develop intelligence, not just skills?” → BND–WHAT-IT-DOES–VALUE-PREP: (rank 1)
- “what is the problem tuple for this RAG (role + pain points)?” → BND-SCOPE-PROBLEM (rank 1)
- “summarize the scope and corpus limits for junior-only tech” → BND-SCOPE-OVERVIEW (rank 1)
- “what is in-scope vs out-of-scope for this system?” → BND-SCOPE-BOUNDARY (rank 2)
- “which junior roles are supported right now?” → BND-SCOPE-ROLES-POINTER (rank 1)

## Sample Misses (first 20)
- “what is the end goal of this system for junior roles?”
- “can this improve my IQ for tech roles?”
- “do you include spaced and retrieval practice in the plan?”
- “what's the step-by-step learning flow?”
- “can you guarantee results?”
- “where can I find the General Insight Taxonomy?”
- “what’s the impact of my knowledge perception on the plan?”
- “what causes misalignment in knowledge perception setup?”
- “how do you capture my modality, interactivity, social context, and memory supports?”
- “why do learning preferences matter for my plan?”
- “why does time–energy rhythm matter for scheduling?”
- “what goes wrong if pace tolerance settings are missing?”
- “what are general pain points and how are they scoped?”
- “why do I keep bouncing between resources?”
- “why do my attempts not map cleanly to the goal?”
- “what mental models help with SQL?”
- “which cognitive skills drive data wrangling?”
- “stats topics I must master for data science”
- “why ML algorithm skill moves the needle”
- “which cognitive skills matter for ML modeling?”