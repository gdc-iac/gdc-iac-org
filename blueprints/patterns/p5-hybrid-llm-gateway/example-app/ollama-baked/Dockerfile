FROM ollama/ollama:latest

# Start server silently, pull the weights, then package it into the image
RUN nohup bash -c "ollama serve &" && \
    sleep 5 && \
    ollama pull gemma:7b

ENTRYPOINT ["/bin/ollama"]
CMD ["serve"]
