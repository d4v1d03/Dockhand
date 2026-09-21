"""USD per million tokens: (input, output, cached input). Substring-matched on
the model id; unknown models get no cost. Update when providers change prices."""

PRICES = {
    "deepseek-chat": (0.27, 1.10, 0.07),
    "deepseek-reasoner": (0.55, 2.19, 0.14),
    "qwen3-coder": (1.00, 5.00, 0.20),
    "kimi-k2": (0.60, 2.50, 0.15),
    "glm-4.6": (0.60, 2.20, 0.11),
    "gemini-3.6-flash": (0.30, 2.50, 0.075),
    "gemini-3.8-flash": (0.30, 2.50, 0.075),
    "gemini": (0.30, 2.50, 0.075),
    "gpt-4.1-mini": (0.40, 1.60, 0.10),
}


def cost_usd(model: str, prompt: int, completion: int, cached: int = 0) -> float | None:
    for key, (pin, pout, pcache) in PRICES.items():
        if key in model:
            return ((prompt - cached) * pin + cached * pcache + completion * pout) / 1e6
    return None
