#!/usr/bin/env python3
"""
Flexible SAP OData MCP Server
Intelligent, dynamic interaction with any SAP OData service without restrictions
"""

import json
import sys
import urllib.request
import urllib.parse
import urllib.error
import base64
import os
import re
from typing import Dict, Any, Optional, List


class SAPODataClient:
    """Intelligent SAP OData client with dynamic multi-service capabilities"""
    
    def __init__(self, base_url: str, username: str = None, password: str = None):
        # Handle both base URLs and service-specific URLs
        if '/sap/opu/odata/sap/' in base_url and base_url.count('/') > 5:
            # Extract base URL from service-specific URL
            parts = base_url.split('/sap/opu/odata/sap/')
            self.base_url = parts[0] + '/sap/opu/odata/sap'
            self.current_service = parts[1] if len(parts) > 1 else None
        else:
            self.base_url = base_url.rstrip('/')
            self.current_service = None
            
        self.username = username
        self.password = password
        self._metadata_cache = {}
        self._service_doc_cache = {}
        self._available_services = []
        self._service_catalog = None
    
    def _make_request(self, endpoint: str, params: Dict[str, str] = None, method: str = "GET", data: str = None, service: str = None) -> Dict[str, Any]:
        """Make HTTP request to SAP OData service with full HTTP method support"""
        # Use specified service or current service
        target_service = service or self.current_service
        
        if target_service:
            url = f"{self.base_url}/{target_service}/{endpoint.lstrip('/')}" if endpoint else f"{self.base_url}/{target_service}"
        else:
            url = f"{self.base_url}/{endpoint.lstrip('/')}" if endpoint else self.base_url
        
        if params:
            query_string = urllib.parse.urlencode(params)
            url += f"?{query_string}"
        
        request = urllib.request.Request(url, method=method.upper())
        request.add_header('Accept', 'application/json')
        request.add_header('Content-Type', 'application/json')
        
        # Add CSRF token for write operations
        if method.upper() in ['POST', 'PUT', 'PATCH', 'DELETE']:
            csrf_token = self._get_csrf_token()
            if csrf_token:
                request.add_header('X-CSRF-Token', csrf_token)
        
        # Add basic authentication if credentials provided
        if self.username and self.password:
            auth_string = f"{self.username}:{self.password}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            request.add_header('Authorization', f'Basic {auth_b64}')
        
        # Add request body for write operations
        if data and method.upper() in ['POST', 'PUT', 'PATCH']:
            request.data = data.encode('utf-8')
        
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response_data = response.read().decode('utf-8')
                if response_data.strip():
                    return json.loads(response_data)
                else:
                    return {"status": "success", "message": f"{method} operation completed"}
        except urllib.error.HTTPError as e:
            error_data = e.read().decode('utf-8') if e.fp else str(e)
            try:
                error_json = json.loads(error_data)
                raise Exception(f"HTTP {e.code}: {error_json}")
            except:
                raise Exception(f"HTTP {e.code}: {error_data}")
        except Exception as e:
            raise Exception(f"Request failed: {str(e)}")
    
    def _get_csrf_token(self) -> Optional[str]:
        """Get CSRF token for write operations"""
        try:
            request = urllib.request.Request(self.base_url, method="HEAD")
            request.add_header('X-CSRF-Token', 'fetch')
            if self.username and self.password:
                auth_string = f"{self.username}:{self.password}"
                auth_bytes = auth_string.encode('ascii')
                auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
                request.add_header('Authorization', f'Basic {auth_b64}')
            
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.headers.get('X-CSRF-Token')
        except:
            return None
    
    def get_service_document(self, service: str = None) -> Dict[str, Any]:
        """Get and cache service document"""
        target_service = service or self.current_service or 'default'
        
        if target_service not in self._service_doc_cache:
            self._service_doc_cache[target_service] = self._make_request("", service=service)
        return self._service_doc_cache[target_service]
    
    def get_metadata(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get and parse OData metadata"""
        if not self._metadata_cache or force_refresh:
            try:
                # Try JSON metadata first
                metadata = self._make_request("$metadata", {"$format": "json"})
                self._metadata_cache = metadata
            except:
                # Fallback to service document
                self._metadata_cache = self.get_service_document()
        return self._metadata_cache
    
    def discover_entity_sets(self, service: str = None) -> List[str]:
        """Dynamically discover all available entity sets for a service"""
        service_doc = self.get_service_document(service)
        entity_sets = []
        
        # Handle different OData response formats
        if "d" in service_doc and "EntitySets" in service_doc["d"]:
            entity_sets = service_doc["d"]["EntitySets"]
        elif "value" in service_doc:
            entity_sets = [item["name"] for item in service_doc["value"] if "name" in item]
        elif "EntitySets" in service_doc:
            entity_sets = service_doc["EntitySets"]
        
        return entity_sets
    
    def analyze_entity_structure(self, entity_set: str) -> Dict[str, Any]:
        """Analyze entity structure by sampling data"""
        try:
            sample_data = self._make_request(entity_set, {"$top": "1"})
            
            if "d" in sample_data and "results" in sample_data["d"] and sample_data["d"]["results"]:
                sample_entity = sample_data["d"]["results"][0]
            elif "value" in sample_data and sample_data["value"]:
                sample_entity = sample_data["value"][0]
            else:
                return {"error": "No sample data available"}
            
            # Analyze field types and structure
            structure = {}
            for key, value in sample_entity.items():
                if key.startswith("__"):
                    continue
                structure[key] = {
                    "type": type(value).__name__,
                    "sample_value": str(value)[:100] if len(str(value)) > 100 else value
                }
            
            return {
                "entity_set": entity_set,
                "fields": structure,
                "sample_count": 1
            }
        except Exception as e:
            return {"error": str(e)}
    
    def discover_all_services(self) -> List[Dict[str, Any]]:
        """Discover all available OData services on the SAP system"""
        try:
            # Try SAP Gateway service catalog
            catalog_url = "/IWFND/CATALOGSERVICE;v=2/ServiceCollection"
            catalog_data = self._make_request(catalog_url, service=None)
            
            services = []
            if "d" in catalog_data and "results" in catalog_data["d"]:
                for service in catalog_data["d"]["results"]:
                    services.append({
                        "name": service.get("TechnicalServiceName", service.get("ServiceId", "Unknown")),
                        "description": service.get("ServiceDescription", service.get("Title", "")),
                        "version": service.get("ServiceVersion", "1")
                    })
            elif "value" in catalog_data:
                for service in catalog_data["value"]:
                    services.append({
                        "name": service.get("TechnicalServiceName", service.get("ServiceId", "Unknown")),
                        "description": service.get("ServiceDescription", service.get("Title", "")),
                        "version": service.get("ServiceVersion", "1")
                    })
            
            self._available_services = services
            return services
            
        except:
            # Fallback: try common service patterns
            common_services = [
                "API_CUSTOMER_SRV", "API_BILLING_DOCUMENT_SRV", "API_SALES_ORDER_SRV",
                "API_MATERIAL_SRV", "API_SUPPLIER_SRV", "API_FINANCIALSTATEMENT_SRV",
                "API_PURCHASE_ORDER_SRV", "API_BUSINESS_PARTNER_SRV"
            ]
            
            available_services = []
            for service_name in common_services:
                try:
                    # Test if service exists
                    self._make_request("", service=service_name)
                    available_services.append({
                        "name": service_name,
                        "description": f"SAP {service_name.replace('API_', '').replace('_SRV', '')} Service",
                        "version": "1"
                    })
                except:
                    continue
            
            self._available_services = available_services
            return available_services
    
    def find_service_for_entity(self, entity_name: str) -> Optional[str]:
        """Intelligently find which service contains a specific entity"""
        # Try current service first
        if self.current_service:
            try:
                entities = self.discover_entity_sets(self.current_service)
                if entity_name in entities:
                    return self.current_service
            except:
                pass
        
        # Search through all available services
        if not self._available_services:
            self.discover_all_services()
        
        for service_info in self._available_services:
            service_name = service_info["name"]
            try:
                entities = self.discover_entity_sets(service_name)
                if entity_name in entities:
                    return service_name
            except:
                continue
        
        return None
    
    def switch_service(self, service_name: str) -> bool:
        """Switch to a different OData service"""
        try:
            # Test if service is accessible
            self.get_service_document(service_name)
            self.current_service = service_name
            return True
        except:
            return False
    
    def get_service_info(self) -> Dict[str, Any]:
        """Get information about current service and available services"""
        return {
            "current_service": self.current_service,
            "base_url": self.base_url,
            "available_services": len(self._available_services),
            "services": self._available_services
        }


class FlexibleSAPMCPServer:
    def __init__(self):
        self.sap_client = None
        self._load_sap_config()
        
        self.tools = {
            "echo": {
                "description": "Echo back the input message",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Message to echo back"}
                    },
                    "required": ["message"]
                }
            },
            "sap_query": {
                "description": "Flexible SAP OData query with full OData capabilities",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_set": {"type": "string", "description": "OData entity set to query"},
                        "filter": {"type": "string", "description": "OData $filter parameter"},
                        "select": {"type": "string", "description": "OData $select parameter"},
                        "expand": {"type": "string", "description": "OData $expand parameter"},
                        "orderby": {"type": "string", "description": "OData $orderby parameter"},
                        "top": {"type": "integer", "description": "OData $top parameter"},
                        "skip": {"type": "integer", "description": "OData $skip parameter"},
                        "count": {"type": "boolean", "description": "Include $count=true"},
                        "format": {"type": "string", "description": "Response format (json/xml)"}
                    },
                    "required": ["entity_set"]
                }
            },
            "sap_create": {
                "description": "Create new entity in SAP system",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_set": {"type": "string", "description": "Entity set to create in"},
                        "data": {"type": "object", "description": "Entity data as JSON object"}
                    },
                    "required": ["entity_set", "data"]
                }
            },
            "sap_update": {
                "description": "Update existing entity in SAP system",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_key": {"type": "string", "description": "Entity key/path to update"},
                        "data": {"type": "object", "description": "Updated entity data as JSON object"},
                        "method": {"type": "string", "enum": ["PUT", "PATCH"], "description": "Update method (PUT=replace, PATCH=merge)"}
                    },
                    "required": ["entity_key", "data"]
                }
            },
            "sap_delete": {
                "description": "Delete entity from SAP system",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_key": {"type": "string", "description": "Entity key/path to delete"}
                    },
                    "required": ["entity_key"]
                }
            },
            "sap_function": {
                "description": "Call SAP function import",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "function_name": {"type": "string", "description": "Function import name"},
                        "parameters": {"type": "object", "description": "Function parameters as JSON object"}
                    },
                    "required": ["function_name"]
                }
            },
            "sap_batch": {
                "description": "Execute multiple OData operations in a batch",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operations": {
                            "type": "array",
                            "description": "Array of operations to execute",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "method": {"type": "string"},
                                    "url": {"type": "string"},
                                    "data": {"type": "object"}
                                }
                            }
                        }
                    },
                    "required": ["operations"]
                }
            },
            "sap_discover": {
                "description": "Discover and analyze SAP service structure",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_set": {"type": "string", "description": "Specific entity set to analyze (optional)"},
                        "deep_analysis": {"type": "boolean", "description": "Perform deep structure analysis"}
                    }
                }
            },
            "sap_metadata": {
                "description": "Get comprehensive SAP service metadata",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "format": {"type": "string", "enum": ["summary", "detailed"], "description": "Metadata detail level"}
                    }
                }
            },
            "sap_test_connection": {
                "description": "Test SAP connection and show configuration status",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            "sap_raw_request": {
                "description": "Make raw HTTP request to SAP system for maximum flexibility",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "endpoint": {"type": "string", "description": "API endpoint path"},
                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"], "description": "HTTP method"},
                        "parameters": {"type": "object", "description": "Query parameters"},
                        "data": {"type": "object", "description": "Request body data"}
                    },
                    "required": ["endpoint"]
                }
            },
            "sap_discover_services": {
                "description": "Discover all available SAP OData services on the system",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Filter services by pattern (optional)"}
                    }
                }
            },
            "sap_switch_service": {
                "description": "Switch to a different OData service",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string", "description": "Name of the service to switch to"}
                    },
                    "required": ["service_name"]
                }
            },
            "sap_smart_query": {
                "description": "Intelligently query entities across all services (auto-discovers optimal service)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity_set": {"type": "string", "description": "OData entity set to query"},
                        "filter": {"type": "string", "description": "OData $filter parameter"},
                        "select": {"type": "string", "description": "OData $select parameter"},
                        "top": {"type": "integer", "description": "OData $top parameter"}
                    },
                    "required": ["entity_set"]
                }
            },
            "sap_service_info": {
                "description": "Get information about current service and available services",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    
    def _load_sap_config(self):
        """Load SAP config from .env file"""
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(script_dir, '.env')
        
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
                
                print("✓ Successfully loaded .env file", file=sys.stderr)
                
                base_url = os.environ.get('SAP_URL')
                username = os.environ.get('SAP_USERNAME')
                password = os.environ.get('SAP_PASSWORD')
                
                if base_url:
                    self.sap_client = SAPODataClient(base_url, username, password)
                    auth_info = "with auth" if username else "without auth"
                    print(f"✓ SAP client configured {auth_info}", file=sys.stderr)
                else:
                    print("✗ SAP_URL not found in .env file", file=sys.stderr)
                    
            except Exception as e:
                print(f"✗ Failed to load .env file: {str(e)}", file=sys.stderr)
        else:
            print("ℹ Create .env file with SAP_URL, SAP_USERNAME, SAP_PASSWORD", file=sys.stderr)
    
    def handle_message(self, message):
        """Handle incoming JSON-RPC messages"""
        try:
            data = json.loads(message)
            method = data.get("method")
            params = data.get("params", {})
            msg_id = data.get("id", "unknown")
            
            if method == "initialize":
                return self.initialize_response(msg_id)
            elif method == "tools/list":
                return self.list_tools_response(msg_id)
            elif method == "tools/call":
                return self.call_tool_response(msg_id, params)
            else:
                return self.error_response(msg_id, f"Unknown method: {method}")
        
        except Exception as e:
            return self.error_response(None, f"Error parsing message: {str(e)}")
    
    def initialize_response(self, msg_id):
        return json.dumps({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "flexible-sap-mcp", "version": "2.0.0"}
            }
        })
    
    def list_tools_response(self, msg_id):
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
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not self.sap_client and tool_name != "echo":
            return self.error_response(msg_id, "SAP not configured. Create .env file with SAP_URL.")
        
        try:
            if tool_name == "echo":
                result = self.echo_tool(arguments)
            elif tool_name == "sap_query":
                result = self.sap_query_tool(arguments)
            elif tool_name == "sap_create":
                result = self.sap_create_tool(arguments)
            elif tool_name == "sap_update":
                result = self.sap_update_tool(arguments)
            elif tool_name == "sap_delete":
                result = self.sap_delete_tool(arguments)
            elif tool_name == "sap_function":
                result = self.sap_function_tool(arguments)
            elif tool_name == "sap_batch":
                result = self.sap_batch_tool(arguments)
            elif tool_name == "sap_discover":
                result = self.sap_discover_tool(arguments)
            elif tool_name == "sap_metadata":
                result = self.sap_metadata_tool(arguments)
            elif tool_name == "sap_test_connection":
                result = self.sap_test_connection_tool(arguments)
            elif tool_name == "sap_raw_request":
                result = self.sap_raw_request_tool(arguments)
            elif tool_name == "sap_discover_services":
                result = self.sap_discover_services_tool(arguments)
            elif tool_name == "sap_switch_service":
                result = self.sap_switch_service_tool(arguments)
            elif tool_name == "sap_smart_query":
                result = self.sap_smart_query_tool(arguments)
            elif tool_name == "sap_service_info":
                result = self.sap_service_info_tool(arguments)
            else:
                return self.error_response(msg_id, f"Unknown tool: {tool_name}")
            
            return json.dumps({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": result}]}
            })
        
        except Exception as e:
            return self.error_response(msg_id, f"Tool error in {tool_name}: {str(e)}")
    
    def echo_tool(self, args):
        """Echo back the input message"""
        message = args["message"]
        return f"Echo: {message}"
    
    def sap_query_tool(self, args):
        """Flexible SAP OData query"""
        entity_set = args["entity_set"]
        
        # Build comprehensive OData query parameters
        params = {}
        if args.get("filter"):
            params["$filter"] = args["filter"]
        if args.get("select"):
            params["$select"] = args["select"]
        if args.get("expand"):
            params["$expand"] = args["expand"]
        if args.get("orderby"):
            params["$orderby"] = args["orderby"]
        if args.get("top"):
            params["$top"] = str(args["top"])
        if args.get("skip"):
            params["$skip"] = str(args["skip"])
        if args.get("count"):
            params["$count"] = "true"
        if args.get("format"):
            params["$format"] = args["format"]
        
        data = self.sap_client._make_request(entity_set, params)
        
        # Format response with metadata
        result_info = self._format_query_result(data, entity_set, params)
        return result_info
    
    def sap_create_tool(self, args):
        """Create new entity in SAP"""
        entity_set = args["entity_set"]
        entity_data = args["data"]
        
        data_json = json.dumps(entity_data)
        result = self.sap_client._make_request(entity_set, method="POST", data=data_json)
        
        return f"✅ Created new entity in {entity_set}:\n{json.dumps(result, indent=2)}"
    
    def sap_update_tool(self, args):
        """Update existing entity in SAP"""
        entity_key = args["entity_key"]
        entity_data = args["data"]
        method = args.get("method", "PATCH")
        
        data_json = json.dumps(entity_data)
        result = self.sap_client._make_request(entity_key, method=method, data=data_json)
        
        return f"✅ Updated entity {entity_key} using {method}:\n{json.dumps(result, indent=2)}"
    
    def sap_delete_tool(self, args):
        """Delete entity from SAP"""
        entity_key = args["entity_key"]
        
        result = self.sap_client._make_request(entity_key, method="DELETE")
        
        return f"✅ Deleted entity {entity_key}:\n{json.dumps(result, indent=2)}"
    
    def sap_function_tool(self, args):
        """Call SAP function import"""
        function_name = args["function_name"]
        function_params = args.get("parameters", {})
        
        # Build function call URL
        if function_params:
            param_string = ",".join([f"{k}='{v}'" for k, v in function_params.items()])
            endpoint = f"{function_name}({param_string})"
        else:
            endpoint = function_name
        
        result = self.sap_client._make_request(endpoint, method="POST")
        
        return f"📞 Function {function_name} result:\n{json.dumps(result, indent=2)}"
    
    def sap_batch_tool(self, args):
        """Execute batch operations (simplified implementation)"""
        operations = args["operations"]
        
        results = []
        for i, operation in enumerate(operations):
            try:
                method = operation.get("method", "GET")
                url = operation.get("url", "")
                data = operation.get("data")
                
                data_json = json.dumps(data) if data else None
                result = self.sap_client._make_request(url, method=method, data=data_json)
                results.append({
                    "operation": i + 1,
                    "status": "success",
                    "result": result
                })
            except Exception as e:
                results.append({
                    "operation": i + 1,
                    "status": "error",
                    "error": str(e)
                })
        
        return f"📦 Batch operation results:\n{json.dumps(results, indent=2)}"
    
    def sap_discover_tool(self, args):
        """Discover and analyze SAP service structure"""
        entity_set = args.get("entity_set")
        deep_analysis = args.get("deep_analysis", False)
        
        if entity_set:
            # Analyze specific entity set
            structure = self.sap_client.analyze_entity_structure(entity_set)
            return f"🔍 Entity Analysis for {entity_set}:\n{json.dumps(structure, indent=2)}"
        else:
            # Discover all entity sets
            entity_sets = self.sap_client.discover_entity_sets()
            
            if deep_analysis and entity_sets:
                # Analyze first few entity sets as examples
                analyses = {}
                for entity in entity_sets[:3]:  # Analyze first 3 as samples
                    analyses[entity] = self.sap_client.analyze_entity_structure(entity)
                
                return f"""🔍 SAP Service Discovery:

📊 Available Entity Sets ({len(entity_sets)}):
{chr(10).join([f"- {entity}" for entity in entity_sets])}

📋 Sample Entity Structures:
{json.dumps(analyses, indent=2)}"""
            else:
                return f"""🔍 SAP Service Discovery:

📊 Available Entity Sets ({len(entity_sets)}):
{chr(10).join([f"- {entity}" for entity in entity_sets])}

💡 Use deep_analysis=true for detailed structure analysis"""
    
    def sap_metadata_tool(self, args):
        """Get comprehensive SAP service metadata"""
        format_type = args.get("format", "summary")
        
        try:
            metadata = self.sap_client.get_metadata()
            entity_sets = self.sap_client.discover_entity_sets()
            
            if format_type == "detailed":
                return f"""📋 Detailed SAP Metadata:

🌐 Service Information:
{json.dumps(metadata, indent=2)}

📊 Entity Sets ({len(entity_sets)}):
{chr(10).join([f"- {entity}" for entity in entity_sets])}"""
            else:
                return f"""📋 SAP Service Summary:

🔗 Base URL: {self.sap_client.base_url}
📊 Entity Sets: {len(entity_sets)}
🛠️ Available Operations: Query, Create, Update, Delete, Functions

📝 Entity Sets:
{chr(10).join([f"- {entity}" for entity in entity_sets])}

💡 Use format="detailed" for full metadata"""
        except Exception as e:
            return f"❌ Error retrieving metadata: {str(e)}"
    
    def sap_test_connection_tool(self, args):
        """Test SAP connection and show comprehensive status"""
        if not self.sap_client:
            return "❌ SAP not configured. Create .env file with:\nSAP_URL=your_sap_url\nSAP_USERNAME=your_username (optional)\nSAP_PASSWORD=your_password (optional)"
        
        base_url = os.environ.get('SAP_URL', 'Not set')
        username = os.environ.get('SAP_USERNAME', 'Not set')
        has_password = 'Yes' if os.environ.get('SAP_PASSWORD') else 'No'
        
        try:
            # Test connection and gather comprehensive info
            service_doc = self.sap_client.get_service_document()
            entity_sets = self.sap_client.discover_entity_sets()
            
            # Test CSRF token capability
            csrf_available = "Unknown"
            try:
                csrf_token = self.sap_client._get_csrf_token()
                csrf_available = "Yes" if csrf_token else "No"
            except:
                csrf_available = "No"
            
            return f"""✅ SAP Connection Status: SUCCESS

🔧 Configuration:
- URL: {base_url}
- Username: {username}
- Password: {has_password}
- CSRF Support: {csrf_available}

📊 Service Capabilities:
- Entity Sets: {len(entity_sets)}
- Read Operations: ✅ Available
- Write Operations: {'✅ Available' if csrf_available == 'Yes' else '⚠️ Limited'}
- Function Imports: ✅ Available
- Batch Operations: ✅ Available

🛠️ Available Tools:
- sap_query (flexible querying)
- sap_create (create entities)
- sap_update (update entities)
- sap_delete (delete entities)
- sap_function (call functions)
- sap_batch (batch operations)
- sap_discover (explore structure)
- sap_raw_request (maximum flexibility)

Ready for intelligent SAP interaction! 🚀"""
            
        except Exception as e:
            error_msg = str(e)
            if "nodename nor servname provided" in error_msg:
                diagnosis = "❌ DNS Resolution Error - Check SAP server hostname"
            elif "timed out" in error_msg:
                diagnosis = "❌ Connection Timeout - Check SAP server accessibility"
            elif "401" in error_msg:
                diagnosis = "❌ Authentication Error - Check credentials"
            elif "404" in error_msg:
                diagnosis = "❌ Service Not Found - Check OData service URL"
            else:
                diagnosis = f"❌ Connection Error: {error_msg}"
            
            return f"""❌ SAP Connection Status: FAILED

🔧 Configuration:
- URL: {base_url}
- Username: {username}
- Password: {has_password}

🔍 Diagnosis: {diagnosis}

Please check your .env file configuration and network connectivity."""
    
    def sap_raw_request_tool(self, args):
        """Make raw HTTP request for maximum flexibility"""
        endpoint = args["endpoint"]
        method = args.get("method", "GET")
        parameters = args.get("parameters", {})
        data = args.get("data")
        
        data_json = json.dumps(data) if data else None
        result = self.sap_client._make_request(endpoint, parameters, method, data_json)
        
        return f"🔧 Raw {method} request to {endpoint}:\n{json.dumps(result, indent=2)}"
    
    def sap_discover_services_tool(self, args):
        """Discover all available SAP OData services"""
        pattern = args.get("pattern")
        
        services = self.sap_client.discover_all_services()
        
        if pattern:
            # Filter services by pattern
            filtered_services = [s for s in services if pattern.lower() in s["name"].lower() or pattern.lower() in s["description"].lower()]
            services = filtered_services
        
        if not services:
            return "❌ No SAP OData services found. Check system connectivity and permissions."
        
        service_list = "\n".join([f"- {s['name']}: {s['description']}" for s in services])
        
        return f"""🔍 Discovered SAP OData Services ({len(services)}):

{service_list}

💡 Use sap_switch_service to change to a specific service
💡 Use sap_smart_query to automatically find the right service for an entity"""
    
    def sap_switch_service_tool(self, args):
        """Switch to a different OData service"""
        service_name = args["service_name"]
        
        if self.sap_client.switch_service(service_name):
            return f"✅ Successfully switched to service: {service_name}"
        else:
            return f"❌ Failed to switch to service: {service_name}. Service may not exist or be accessible."
    
    def sap_smart_query_tool(self, args):
        """Intelligently query entities across all services"""
        entity_set = args["entity_set"]
        
        # Find the optimal service for this entity
        optimal_service = self.sap_client.find_service_for_entity(entity_set)
        
        if not optimal_service:
            # Try to discover services first
            self.sap_client.discover_all_services()
            optimal_service = self.sap_client.find_service_for_entity(entity_set)
        
        if optimal_service:
            # Switch to optimal service
            current_service = self.sap_client.current_service
            self.sap_client.switch_service(optimal_service)
            
            try:
                # Execute the query using regular sap_query logic
                result = self.sap_query_tool(args)
                return f"🎯 Auto-discovered entity '{entity_set}' in service '{optimal_service}':\n\n{result}"
            finally:
                # Restore original service
                if current_service:
                    self.sap_client.switch_service(current_service)
        else:
            available_services = len(self.sap_client._available_services)
            return f"❌ Entity '{entity_set}' not found in any of the {available_services} available services. Use sap_discover_services to see all services."
    
    def sap_service_info_tool(self, args):
        """Get comprehensive service information"""
        info = self.sap_client.get_service_info()
        
        current_service = info["current_service"] or "None"
        base_url = info["base_url"]
        service_count = info["available_services"]
        
        if service_count == 0:
            # Try to discover services
            self.sap_client.discover_all_services()
            info = self.sap_client.get_service_info()
            service_count = info["available_services"]
        
        services_list = "\n".join([f"- {s['name']}: {s['description']}" for s in info["services"][:10]])  # Show first 10
        more_services = f"\n... and {service_count - 10} more" if service_count > 10 else ""
        
        return f"""📊 SAP Service Information:

🔧 Configuration:
- Base URL: {base_url}
- Current Service: {current_service}
- Available Services: {service_count}

📋 Available Services:
{services_list}{more_services}

🛠️ Available Operations:
- sap_switch_service: Change active service
- sap_smart_query: Auto-find service for entity
- sap_discover_services: Find all services
- sap_query: Query current service"""
    
    def _format_query_result(self, data: Dict[str, Any], entity_set: str, params: Dict[str, str]) -> str:
        """Format query results with comprehensive information"""
        # Extract results based on OData format
        if "d" in data and "results" in data["d"]:
            results = data["d"]["results"]
            count_info = f" (Total: {data['d'].get('__count', 'unknown')})" if "__count" in data.get("d", {}) else ""
        elif "value" in data:
            results = data["value"]
            count_info = f" (Total: {data.get('@odata.count', 'unknown')})" if "@odata.count" in data else ""
        else:
            return f"📊 {entity_set} Response:\n{json.dumps(data, indent=2)}"
        
        result_count = len(results)
        
        # Build query summary
        query_summary = []
        if params.get("$filter"):
            query_summary.append(f"Filter: {params['$filter']}")
        if params.get("$select"):
            query_summary.append(f"Select: {params['$select']}")
        if params.get("$expand"):
            query_summary.append(f"Expand: {params['$expand']}")
        if params.get("$orderby"):
            query_summary.append(f"Order: {params['$orderby']}")
        if params.get("$top"):
            query_summary.append(f"Top: {params['$top']}")
        if params.get("$skip"):
            query_summary.append(f"Skip: {params['$skip']}")
        
        query_info = f"Query: {', '.join(query_summary)}" if query_summary else "Query: All records"
        
        return f"""📊 SAP Query Results for {entity_set}:

🔍 {query_info}
📈 Records: {result_count}{count_info}

📋 Data:
{json.dumps(results, indent=2)}"""
    
    def error_response(self, msg_id, error_msg):
        return json.dumps({
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -1, "message": error_msg}
        })


def main():
    server = FlexibleSAPMCPServer()
    
    print("🚀 Flexible SAP OData MCP Server started", file=sys.stderr)
    print("🛠️  Available tools: echo, sap_query, sap_create, sap_update, sap_delete,", file=sys.stderr)
    print("     sap_function, sap_batch, sap_discover, sap_metadata, sap_test_connection,", file=sys.stderr)
    print("     sap_raw_request, sap_discover_services, sap_switch_service, sap_smart_query, sap_service_info", file=sys.stderr)
    print("🎯 Intelligent, multi-service SAP integration ready!", file=sys.stderr)
    
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