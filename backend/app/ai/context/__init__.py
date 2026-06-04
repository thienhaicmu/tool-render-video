"""AI context layer — collects creator / channel / market signals fed to
the AI Director before it emits a RenderPlan.

Sprint 3: ships CreatorContextBuilder (a thin fetch-+-future-enrichment
wrapper around creator_repo.get_creator_context). Sprint 4 will replace
the static `editorial_hint` plumbing in llm_pipeline.py with a richer
plan input derived from this layer.
"""
