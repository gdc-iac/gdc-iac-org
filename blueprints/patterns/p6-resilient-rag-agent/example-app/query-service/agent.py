import datetime
import json
from utils import get_db_connection, get_embedding, call_gemini_api, call_llm

class Agent:
    def __init__(self, user=None):
        self.user = user
        self.tools = {
            "search_knowledge_base": self.search_knowledge_base,
            "list_documents": self.list_documents,
            "read_document": self.read_document,
            "get_current_time": self.get_current_time
        }
    
    def get_tool_descriptions(self):
        return """
search_knowledge_base: Semantic search for relevant documents. Input: query string.
list_documents: See what files are available. Input: "all" or empty string.
read_document: Read specific document content. Input: filename.
get_current_time: Get system time. Input: "now" or empty string.
"""

    def search_knowledge_base(self, query):
        try:
            # Clean query
            query = query.strip('"').strip("'")
            vec = get_embedding(query)
            conn = get_db_connection()
            cur = conn.cursor()
            
            # RBAC Filter
            user_id = self.user.id if self.user else "anonymous"
            # Admin sees all? Maybe not personal ones unless explicitly requested? 
            # For now, Admin sees shared + their own. 
            # If we want Admin to see ALL, we check self.user.role == 'admin'.
            # Plan says: "Personal Store: Accessible only by the owner". So Admin does NOT see user files by default in search.
            
            cur.execute("""
                SELECT content, filename, 1 - (embedding <=> %s::vector) as similarity
                FROM documents
                WHERE (owner_id IS NULL OR owner_id = %s)
                ORDER BY similarity DESC
                LIMIT 5;
            """, (vec, user_id))
            
            rows = cur.fetchall()
            cur.close()
            conn.close()
            
            if not rows:
                return "No relevant documents found."
            
            results = []
            for row in rows:
                # Truncate content for context window
                results.append(f"Source: {row[1]}\nContent: {row[0][:500]}...") 
            return "\n\n".join(results)
        except Exception as e:
            return f"Error searching knowledge base: {str(e)}"

    def list_documents(self, _):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            user_id = self.user.id if self.user else "anonymous"
            cur.execute("SELECT filename FROM documents WHERE (owner_id IS NULL OR owner_id = %s) LIMIT 50;", (user_id,))
            rows = cur.fetchall()
            cur.close()
            conn.close()
            if not rows:
                return "No documents found."
            return ", ".join([r[0] for r in rows])
        except Exception as e:
            return f"Error listing documents: {str(e)}"

    def read_document(self, filename):
        try:
            filename = filename.strip('"').strip("'")
            conn = get_db_connection()
            cur = conn.cursor()
            user_id = self.user.id if self.user else "anonymous"
            cur.execute("SELECT content FROM documents WHERE filename = %s AND (owner_id IS NULL OR owner_id = %s);", (filename, user_id))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                return row[0][:2000] # Limit content length
            return "Document not found or access denied."
        except Exception as e:
            return f"Error reading document: {str(e)}"

    def get_current_time(self, _):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def run(self, user_query):
        tool_names = ", ".join(self.tools.keys())
        system_prompt = f"""You are a helpful GDC Assistant. You have access to the following local tools:

{self.get_tool_descriptions()}

Use the following format:
Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {user_query}

Important: If the user asks about documents, you MUST use the 'search_knowledge_base' or 'list_documents' tool. Do not answer from your own knowledge.
Example:
Question: What documents mention GDC?
Thought: I need to search for documents containing "GDC".
Action: search_knowledge_base
Action Input: "GDC"
Observation: [System will provide this]

Hint: If your search returns no results, try searching for synonyms or related terms (e.g., "roles" instead of "personas").
"""
        
        history = system_prompt
        thoughts = []
        
        last_action = None
        
        try:
            for step in range(6): # Max 6 steps
                print(f"--- Step {step + 1} ---")
                # Call LLM
                response = await call_gemini_api(history)
                response = response.strip()
                
                # Client-side stop sequence (Backup)
                if "Observation:" in response:
                    response = response.split("Observation:")[0].strip()
                
                print(f"LLM Response: {response}")
                
                # Append to history
                history += f"\n{response}"
                
                # Extract thought for UI (heuristic)
                if "Thought:" in response:
                    parts = response.split("Thought:")
                    latest_thought_block = parts[-1]
                    thought_text = latest_thought_block.split("Action:")[0].split("Final Answer:")[0].strip()
                    if thought_text and thought_text not in thoughts:
                        thoughts.append(thought_text)
                
                if "Final Answer:" in response:
                    final_answer = response.split("Final Answer:")[-1].strip()
                    return {
                        "answer": final_answer,
                        "thoughts": thoughts,
                        "source_document": "Agentic Search",
                        "context_used": history
                    }
                
                if "Action:" in response and "Action Input:" in response:
                    try:
                        action_part = response.split("Action:")[-1]
                        action = action_part.split("Action Input:")[0].strip()
                        action_input = action_part.split("Action Input:")[-1].strip().split("\n")[0].strip()
                        
                        print(f"Action: {action}, Input: {action_input}")
                        
                        # Loop Detection
                        current_action_signature = f"{action}:{action_input}"
                        if current_action_signature == last_action:
                            observation = "Error: You just took this action. Do not repeat it. Use the observation above to answer."
                        else:
                            last_action = current_action_signature
                            # Execute Tool
                            if action in self.tools:
                                observation = self.tools[action](action_input)
                            else:
                                observation = f"Error: Tool '{action}' not found. Available tools: {tool_names}"
                        
                    except Exception as e:
                        observation = f"Error parsing action: {str(e)}"
                    
                    observation_str = f"\nObservation: {observation}"
                    print(f"Observation: {observation[:100]}...")
                    history += observation_str
                else:
                    # If no action and no final answer, assume the model is answering directly or confused.
                    return {
                        "answer": response,
                        "thoughts": thoughts,
                        "source_document": "Direct Response",
                        "context_used": history
                    }
            
            # Fallback if loop finishes without answer
            raise Exception("Agent loop timed out")

        except Exception as e:
            print(f"Agent failed, falling back to simple RAG: {e}")
            # Fallback: Simple RAG
            context = self.search_knowledge_base(user_query)
            fallback_prompt = f"Context:\n{context}\n\nQuestion: {user_query}\nAnswer:"
            fallback_answer = await call_gemini_api(fallback_prompt)
            return {
                "answer": fallback_answer,
                "thoughts": thoughts + ["Agent failed. Falling back to simple RAG search."],
                "source_document": "Fallback RAG",
                "context_used": context
            }
        
        return {
            "answer": "I reached the step limit before finding a final answer.",
            "thoughts": thoughts,
            "source_document": "Timeout",
            "context_used": history
        }
