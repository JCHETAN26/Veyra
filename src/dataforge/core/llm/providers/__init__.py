"""Provider adapters.

Each provider module defines a `*Provider` class implementing the LLMClient
protocol. They are constructed by the factory in `dataforge.core.llm.factory`
and never instantiated directly by application code.
"""
