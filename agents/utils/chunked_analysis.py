import time
import logging
from pathlib import Path

try:
    import config as _config
    _DEFAULT_MAX_TOKENS = getattr(_config, "GEMINI_MAX_TOKENS_REBUY", 6000)
except ImportError:
    _DEFAULT_MAX_TOKENS = 6000

logger = logging.getLogger(__name__)

CHUNK_SIZE = 8
INTER_CHUNK_SLEEP = 5.0  # seconds between chunks — Gemini rate limit guard


def run_chunked_analysis(
    investable: list[dict],
    bundle_path: Path,
    composite_hash: str,
    build_user_prompt_fn,
    response_schema,
    system_instruction: str,
    portfolio_context: dict,
    ask_gemini_fn,
    max_tokens: int | None = None,
) -> tuple[list, list, list, list[str]]:
    """
    Splits investable positions into chunks of CHUNK_SIZE, runs each through
    Gemini, and merges the results.

    Returns: (all_candidates, all_excluded, all_coverage_warnings, chunk_errors)

    CRITICAL: composite_hash is the hash from the ORIGINAL bundle, passed in by
    the caller. It is NEVER taken from a chunk response. This preserves provenance.
    """
    token_budget = max_tokens if max_tokens is not None else _DEFAULT_MAX_TOKENS

    chunks = [
        investable[i : i + CHUNK_SIZE]
        for i in range(0, len(investable), CHUNK_SIZE)
    ]

    logger.info(
        "Chunked execution: %d positions -> %d chunk(s) of <=%d  max_tokens=%d",
        len(investable), len(chunks), CHUNK_SIZE, token_budget,
    )

    all_candidates = []
    all_excluded = []
    all_warnings = []
    chunk_errors = []

    for idx, chunk in enumerate(chunks):
        tickers_in_chunk = [p["ticker"] for p in chunk]
        logger.info("Chunk %d/%d: %s", idx + 1, len(chunks), tickers_in_chunk)

        try:
            user_prompt = build_user_prompt_fn(chunk, portfolio_context)
            result = ask_gemini_fn(
                prompt=user_prompt,
                composite_bundle_path=bundle_path,
                response_schema=response_schema,
                system_instruction=system_instruction,
                max_tokens=token_budget,
            )

            if result is None:
                msg = f"Chunk {idx + 1}/{len(chunks)} ({tickers_in_chunk}): Gemini returned None"
                logger.warning(msg)
                chunk_errors.append(msg)
            else:
                if hasattr(result, "candidates") and result.candidates:
                    all_candidates.extend(result.candidates)
                if hasattr(result, "excluded_tickers") and result.excluded_tickers:
                    all_excluded.extend(result.excluded_tickers)
                if hasattr(result, "coverage_warnings") and result.coverage_warnings:
                    all_warnings.extend(result.coverage_warnings)

        except Exception as e:
            msg = f"Chunk {idx + 1}/{len(chunks)} failed: {e}"
            logger.error(msg, exc_info=True)
            chunk_errors.append(msg)

        if idx < len(chunks) - 1:
            time.sleep(INTER_CHUNK_SLEEP)

    return all_candidates, all_excluded, all_warnings, chunk_errors
