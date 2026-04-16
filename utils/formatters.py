"""
utils/formatters.py — Text formatting utilities.
"""

def dicts_to_markdown_table(data: list[dict]) -> str:
    """
    Converts a list of dictionaries into a Markdown table string.
    Expects flat dictionaries.
    """
    if not data:
        return "No data available."
    
    headers = list(data[0].keys())
    
    # Create the header row
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    
    # Create the data rows
    data_lines = []
    for row in data:
        row_values = [str(row.get(h, "")) for h in headers]
        data_lines.append("| " + " | ".join(row_values) + " |")
    
    return "\n".join([header_line, separator_line] + data_lines)
