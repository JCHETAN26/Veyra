"""Shared, versioned contracts.

These Pydantic models are the *only* sanctioned way modules exchange data.
Keeping them here (rather than importing one module's internals into another)
preserves the clean boundary that lets us split modules into services later.
"""
