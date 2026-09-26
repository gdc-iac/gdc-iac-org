import time
import json
from locust import HttpUser, task, between, events

class GemmaGatewayUser(HttpUser):
    """Locust user simulating concurrent streaming chat completions requests to the gateway."""
    wait_time = between(1, 3)

    @task
    def stream_chat_completion(self):
        payload = {
            "model": "gemma4:26b",
            "messages": [
                {"role": "user", "content": "Explain Mixture of Experts routing algorithms in three sentences."}
            ],
            "temperature": 0.7,
            "stream": True
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        start_time = time.perf_counter()
        ttft = None
        total_response_time = None
        token_count = 0
        chunk_timestamps = []
        
        try:
            # Use stream=True to process the SSE chunks line-by-line
            with self.client.post("/v1/chat/completions", json=payload, headers=headers, stream=True, catch_response=True) as response:
                if response.status_code != 200:
                    response.failure(f"HTTP {response.status_code}: {response.text}")
                    return
                
                for line in response.iter_lines():
                    if line:
                        chunk_time = time.perf_counter()
                        token_count += 1
                        chunk_timestamps.append(chunk_time)
                        
                        # Measure Time to First Token (TTFT)
                        if ttft is None:
                            ttft = (chunk_time - start_time) * 1000  # in milliseconds
                
                end_time = time.perf_counter()
                total_response_time = (end_time - start_time) * 1000
                
                # Record TTFT Event
                if ttft is not None:
                    events.request.fire(
                        request_type="SSE",
                        name="chat_completions_ttft_ms",
                        response_time=ttft,
                        response_length=0,
                        exception=None
                    )
                
                # Record Inter-token Latency Event
                if len(chunk_timestamps) > 1:
                    deltas = [
                        (chunk_timestamps[i] - chunk_timestamps[i-1]) * 1000
                        for i in range(1, len(chunk_timestamps))
                    ]
                    avg_inter_token_latency = sum(deltas) / len(deltas)
                    events.request.fire(
                        request_type="SSE",
                        name="chat_completions_inter_token_latency_ms",
                        response_time=avg_inter_token_latency,
                        response_length=0,
                        exception=None
                    )
                
                # Record Total Stream Event
                events.request.fire(
                    request_type="SSE",
                    name="chat_completions_total_stream_ms",
                    response_time=total_response_time,
                    response_length=token_count,
                    exception=None
                )
                
                response.success()
                
        except Exception as e:
            events.request.fire(
                request_type="SSE",
                name="chat_completions_stream_exception",
                response_time=0,
                response_length=0,
                exception=e
            )
            if 'response' in locals() and response:
                response.failure(f"Exception occurred: {e}")
