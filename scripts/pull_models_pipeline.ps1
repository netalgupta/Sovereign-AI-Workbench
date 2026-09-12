# pull_models_pipeline.ps1
# Sequentially downloads the required workbench models into Ollama

Write-Host "[1/4] Waiting for phi3.5 pull to finish..."
while (-not (ollama list | Select-String "phi3.5")) {
    Start-Sleep -Seconds 10
}
Write-Host "[1/4] phi3.5 is ready!"
Write-Host "Creating alias phi-3.5-mini from phi3.5..."
ollama cp phi3.5 phi-3.5-mini
Write-Host "Model alias phi-3.5-mini ready!"

Write-Host "[2/4] Pulling reasoning-model (qwen2.5:14b - ~9.0 GB)..."
ollama pull qwen2.5:14b
Write-Host "[2/4] qwen2.5:14b is ready!"

Write-Host "[3/4] Pulling coder-model (qwen2.5-coder:7b - ~4.7 GB)..."
ollama pull qwen2.5-coder:7b
Write-Host "[3/4] qwen2.5-coder:7b is ready!"

Write-Host "[4/4] Pulling vision-model (qwen2.5vl:7b - ~6.0 GB)..."
ollama pull qwen2.5vl:7b
Write-Host "[4/4] qwen2.5vl:7b is ready!"

Write-Host "All 4 models successfully pulled! Final Ollama model list:"
ollama list
