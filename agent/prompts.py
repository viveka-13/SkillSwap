# agent/prompts.py
# All LLM prompts for the AutoStartup AI agent

DECOMPOSE_PROMPT = """You are an expert startup analyst and business strategist.

A user has submitted the following startup idea: "{idea}"

Your task is to decompose this idea into 10 specific research and analysis subtasks that an AI agent will execute.

Return ONLY a JSON array of exactly 10 task strings. No explanations, no markdown, just the JSON array.

Example format:
["Task 1: ...", "Task 2: ...", "Task 3: ...", "Task 4: ...", "Task 5: ...", "Task 6: ...", "Task 7: ...", "Task 8: ...", "Task 9: ...", "Task 10: ..."]

Make each task specific, actionable, and relevant to the startup idea. Tasks should cover:
- Market size analysis
- Target audience identification
- Competitor research
- Problem validation
- Solution design
- Feature planning
- Revenue modeling
- Go-to-market strategy
- Technology requirements
- Risk assessment
"""

MARKET_GAP_PROMPT = """You are a startup market analyst.

Startup Idea: {idea}

Market Research Data:
{market_research}

Competitor Analysis:
{competitor_analysis}

Based on this research, identify the TOP 3 market gaps and opportunities. Be specific and data-driven.

Format your response as a clear paragraph (2-3 sentences per gap) covering:
1. What is missing in the current market
2. Why existing solutions fail to address it
3. The opportunity size

Keep it concise and actionable. Maximum 200 words."""

SOLUTION_PROMPT = """You are a product strategist and startup founder.

Startup Idea: {idea}

Market Gap Identified:
{market_gap}

Market Research:
{market_research}

Design a compelling solution strategy. Include:
- Core value proposition (1 sentence)
- How the solution addresses the market gap
- Key differentiators from competitors
- Technology approach (high level)
- Why this will win

Keep it focused and persuasive. Maximum 250 words."""

FEATURES_PROMPT = """You are a product manager for a tech startup.

Startup Idea: {idea}
Solution Strategy: {solution}

Generate exactly 8 core product features. For each feature include the feature name and a 1-sentence description.

Format as a clean list:
1. [Feature Name]: [Brief description]
2. [Feature Name]: [Brief description]
...and so on for 8 features.

Make features specific, valuable, and directly tied to solving the market problem."""

REVENUE_PROMPT = """You are a startup financial strategist.

Startup Idea: {idea}
Solution: {solution}
Target Market: {market_research}

Generate a comprehensive revenue model including:
- Primary revenue stream(s)
- Pricing strategy (specific tiers or pricing)
- Secondary revenue opportunities
- Projected unit economics (rough estimates)
- Path to profitability

Be specific with numbers where possible. Maximum 200 words."""

ROADMAP_PROMPT = """You are a startup CTO and project manager.

Startup Idea: {idea}
Core Features: {features}
Revenue Model: {revenue}

Create a 12-month implementation roadmap with 4 phases:

Phase 1 (Months 1-3): Foundation & MVP
Phase 2 (Months 4-6): Beta Launch & Learning  
Phase 3 (Months 7-9): Growth & Optimization
Phase 4 (Months 10-12): Scale & Expand

For each phase list 3-4 specific milestones. Be concrete and realistic."""

PITCH_PROMPT = """You are a startup pitch coach who has helped companies raise millions.

Startup Idea: {idea}
Solution: {solution}
Revenue Model: {revenue}
Market Research: {market_research}

Create a 10-slide pitch deck outline. For each slide include:
- Slide title
- 2-3 bullet points of what to cover

The slides should follow the standard investor pitch structure:
1. Title/Hook
2. Problem
3. Solution  
4. Market Size
5. Product
6. Business Model
7. Traction/Validation
8. Team (placeholder)
9. Financials
10. Ask/CTA"""

COMPILE_PROMPT = """You are a senior business analyst compiling a complete startup report.

Startup Idea: {idea}
All Research and Analysis: {all_context}

Generate the following in a structured format:

STARTUP_TITLE: [Catchy name for this startup, max 5 words]

PROBLEM_STATEMENT: [2-3 sentences describing the problem being solved]

TARGET_AUDIENCE: [Specific description of who the primary customer is, 2-3 sentences]

EXECUTIVE_SUMMARY: [A compelling 4-5 sentence executive summary that an investor would read. Cover the problem, solution, market opportunity, and why now.]

Return ONLY these 4 sections with exactly these labels. No other text."""
