# sap-odata-mcp-py# SAP OData MCP Server

Connect any AI assistant to your SAP system via OData services.

## Quick Start

1. **Install:**
```bash
python3 mcp_server.py
```

2. **Configure `.env` file:**
```
SAP_URL=https://your-sap-server.com/sap/opu/odata/sap
SAP_USERNAME=your_username  
SAP_PASSWORD=your_password
```

3. **Test:**
```bash
npx @modelcontextprotocol/inspector python3 mcp_server.py
```

## Main Features

- **Auto-discovers** all SAP OData services
- **Query, create, update, delete** SAP data
- **Works with Claude Desktop** and other AI assistants
- **No coding required** - just configure and use

## Key Tools

| Tool | What it does |
|------|-------------|
| `sap_smart_query` | Find and query any entity automatically |
| `sap_discover_services` | See all available SAP services |
| `sap_test_connection` | Check if everything works |


## Claude Desktop Setup

Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "sap": {
      "command": "python3",
      "args": ["/path/to/mcp_server.py"]
    }
  }
}
```

## Troubleshooting

**Connection failed?**
- Check SAP_URL, username, password
- Run `sap_test_connection` to diagnose

**Can't find entity?**
- Run `sap_discover_services` to see what's available
- Use `sap_smart_query` instead of `sap_query`

## What Makes This Special

- Works with **any SAP OData service** 
- **Automatically finds** the right service for your data
- **AI-friendly** - no technical knowledge needed
- **Secure** - credentials in .env file only

Ready to chat with your SAP data! 🚀