import os
import json
from typing import Dict, Any
from openai import OpenAI
from anthropic import Anthropic
from core.data_models import QueryRequest

def generate_sql_with_openai(query_text: str, schema_info: Dict[str, Any]) -> str:
    """
    Generate SQL query using OpenAI API
    """
    try:
        # Get API key from environment
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        client = OpenAI(api_key=api_key)
        
        # Format schema for prompt
        schema_description = format_schema_for_prompt(schema_info)
        
        # Create prompt
        prompt = f"""Given the following database schema:

{schema_description}

Convert this natural language query to SQL: "{query_text}"

Rules:
- Return ONLY the SQL query, no explanations
- Use proper SQLite syntax
- Handle date/time queries appropriately (e.g., "last week" = date('now', '-7 days'))
- Be careful with column names and table names
- If the query is ambiguous, make reasonable assumptions

SQL Query:"""
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a SQL expert. Convert natural language to SQL queries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=500
        )
        
        sql = response.choices[0].message.content.strip()
        
        # Clean up the SQL (remove markdown if present)
        if sql.startswith("```sql"):
            sql = sql[6:]
        if sql.startswith("```"):
            sql = sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        
        return sql.strip()
        
    except Exception as e:
        raise Exception(f"Error generating SQL with OpenAI: {str(e)}")

def generate_sql_with_anthropic(query_text: str, schema_info: Dict[str, Any]) -> str:
    """
    Generate SQL query using Anthropic API
    """
    try:
        # Get API key from environment
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        
        client = Anthropic(api_key=api_key)
        
        # Format schema for prompt
        schema_description = format_schema_for_prompt(schema_info)
        
        # Create prompt
        prompt = f"""Given the following database schema:

{schema_description}

Convert this natural language query to SQL: "{query_text}"

Rules:
- Return ONLY the SQL query, no explanations
- Use proper SQLite syntax
- Handle date/time queries appropriately (e.g., "last week" = date('now', '-7 days'))
- Be careful with column names and table names
- If the query is ambiguous, make reasonable assumptions

SQL Query:"""
        
        # Call Anthropic API
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            temperature=0.1,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        sql = response.content[0].text.strip()
        
        # Clean up the SQL (remove markdown if present)
        if sql.startswith("```sql"):
            sql = sql[6:]
        if sql.startswith("```"):
            sql = sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        
        return sql.strip()
        
    except Exception as e:
        raise Exception(f"Error generating SQL with Anthropic: {str(e)}")

def format_schema_for_prompt(schema_info: Dict[str, Any]) -> str:
    """
    Format database schema for LLM prompt
    """
    lines = []
    
    for table_name, table_info in schema_info.get('tables', {}).items():
        lines.append(f"Table: {table_name}")
        lines.append("Columns:")
        
        for col_name, col_type in table_info['columns'].items():
            lines.append(f"  - {col_name} ({col_type})")
        
        lines.append(f"Row count: {table_info['row_count']}")
        lines.append("")
    
    return "\n".join(lines)

def generate_sql(request: QueryRequest, schema_info: Dict[str, Any]) -> str:
    """
    Route to appropriate LLM provider based on enable flags and API key availability.

    Priority:
    1) ANTHROPIC_ENABLED=true AND ANTHROPIC_API_KEY exists -> use Anthropic
    2) OPENAI_ENABLED=true AND OPENAI_API_KEY exists -> use OpenAI
    3) Fall back to request.llm_provider preference
    4) Error if no provider is configured
    """
    # Read provider enable flags (default Anthropic=true for backward compatibility)
    anthropic_enabled = os.environ.get("ANTHROPIC_ENABLED", "true").lower() == "true"
    openai_enabled = os.environ.get("OPENAI_ENABLED", "true").lower() == "true"

    # Check API keys
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    # Priority 1: Anthropic if enabled and key exists
    if anthropic_enabled and anthropic_key:
        return generate_sql_with_anthropic(request.query, schema_info)

    # Priority 2: OpenAI if enabled and key exists
    if openai_enabled and openai_key:
        return generate_sql_with_openai(request.query, schema_info)

    # Priority 3: Fall back to request preference if key exists
    if request.llm_provider == "openai" and openai_key:
        return generate_sql_with_openai(request.query, schema_info)
    elif request.llm_provider == "anthropic" and anthropic_key:
        return generate_sql_with_anthropic(request.query, schema_info)

    # Priority 4: Error if no provider is configured
    raise ValueError(
        "No LLM provider configured. Set ANTHROPIC_ENABLED=true with ANTHROPIC_API_KEY "
        "or OPENAI_ENABLED=true with OPENAI_API_KEY in your environment."
    )