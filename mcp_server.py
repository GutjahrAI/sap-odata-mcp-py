#!/usr/bin/env python3
"""
Simple MCP Server - Basic Example
Provides a calculator tool and echo tool
"""

import json
import sys
import asyncio


class SimpleMCPServer:
    def __init__(self):
        self.tools = {
            "calculator": {
                "description": "Perform basic math operations",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string", "enum": ["add", "subtract", "multiply", "divide"]},
                        "a": {"type": "number"},
                        "b": {"type": "number"}
                    },
                    "required": ["operation", "a", "b"]
                }
            },
            "echo": {
                "description": "Echo back the input message",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"}
                    },
                    "required": ["message"]
                }
            }
        }
    
    def handle_message(self, message):
        """Handle incoming JSON-RPC messages"""
        try:
            data = json.loads(message)
            method = data.get("method")
            params = data.get("params", {})
            msg_id = data.get("id")
            
            if method == "initialize":
                return self.initialize_response(msg_id)
            elif method == "tools/list":
                return self.list_tools_response(msg_id)
            elif method == "tools/call":
                return self.call_tool_response(msg_id, params)
            else:
                return self.error_response(msg_id, f"Unknown method: {method}")
        
        except Exception as e:
            return self.error_response(None, f"Error: {str(e)}")
    
    def initialize_response(self, msg_id):
        """Return server capabilities"""
        return json.dumps({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "simple-mcp", "version": "1.0.0"}
            }
        })
    
    def list_tools_response(self, msg_id):
        """Return available tools"""
        tools_list = []
        for name, info in self.tools.items():
            tools_list.append({
                "name": name,
                "description": info["description"],
                "inputSchema": info["parameters"]
            })
        
        return json.dumps({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": tools_list}
        })
    
    def call_tool_response(self, msg_id, params):
        """Execute a tool and return results"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        try:
            if tool_name == "calculator":
                result = self.calculator_tool(arguments)
            elif tool_name == "echo":
                result = self.echo_tool(arguments)
            else:
                return self.error_response(msg_id, f"Unknown tool: {tool_name}")
            
            return json.dumps({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": result}]}
            })
        
        except Exception as e:
            return self.error_response(msg_id, f"Tool error: {str(e)}")
    
    def calculator_tool(self, args):
        """Simple calculator implementation"""
        operation = args["operation"]
        a = args["a"]
        b = args["b"]
        
        if operation == "add":
            result = a + b
        elif operation == "subtract":
            result = a - b
        elif operation == "multiply":
            result = a * b
        elif operation == "divide":
            if b == 0:
                raise ValueError("Cannot divide by zero")
            result = a / b
        else:
            raise ValueError(f"Unknown operation: {operation}")
        
        return f"{a} {operation} {b} = {result}"
    
    def echo_tool(self, args):
        """Echo the input message"""
        message = args["message"]
        return f"Echo: {message}"
    
    def error_response(self, msg_id, error_msg):
        """Return error response"""
        return json.dumps({
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -1, "message": error_msg}
        })


def main():
    """Run the MCP server"""
    server = SimpleMCPServer()
    
    print("Simple MCP Server started. Send JSON-RPC messages:", file=sys.stderr)
    
    try:
        for line in sys.stdin:
            line = line.strip()
            if line:
                response = server.handle_message(line)
                print(response)
                sys.stdout.flush()
    except KeyboardInterrupt:
        print("Server stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()