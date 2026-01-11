# RPA Betting Helper

Este projeto fornece um RPA minimal para coletar estatísticas de times e odds de mercado, e aplicar uma avaliação simples (ou usar OpenAI) para sugerir apostas com potencial valor.

## Como usar (passo a passo) ✅

### Pré-requisitos
- **Python 3.8+** (recomendado 3.11+)
- Playwright (opcional, para sites dinâmicos / bloqueados)
- Chave OpenAI (opcional, apenas se quiser usar IA)

### 1) Entre na pasta do projeto
```powershell
Set-Location Z:\Projetos\ProjetosRkz
```

### 2) Criar e ativar ambiente virtual e instalar dependências
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1    # PowerShell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3) (Opcional) Instalar navegadores do Playwright
Se pretende raspar sites que bloqueiam requests simples (403) ou carregam dados via JavaScript, instale os navegadores:
```powershell
pip install playwright
playwright install
```

### 4) Configurar `config.local.yaml`
- Edite as seções `sites` e `leagues` para indicar as ligas e casas de aposta que quer monitorar.
- Exemplo: em `leagues` coloque `name`, `source: sofascore`, `url` (página do torneio no SofaScore) e `max_teams`.

### 5) Configurar chave OpenAI (opcional)
Recomendado usar variável de ambiente:
```powershell
$env:OPENAI_API_KEY = "sk-..."
setx OPENAI_API_KEY "sk-..."   # persistente
```
> Alternativa (não recomendada): colocar a chave em `config.local.yaml` (NÃO comite este arquivo).

### 6) Testar a chave OpenAI (opcional)
```powershell
python test_openai.py
```

### 7) Executar o RPA
```powershell
python runner.py
```

Saída
- O `runner.py` imprime recomendações no console. Para salvar, redirecione a saída:
```powershell
python runner.py > recomendacoes.txt
```
- Você também pode configurar `output.json_file` em `config.local.yaml` para salvar resultados em JSON.

### Depuração (se algo falhar) 🔧
- Se um scraping falhar, o script salva um arquivo `scrape_error_<site>.html` ou `scrape_error_<site>.txt` na pasta do projeto. Abra o `.html` no navegador para inspecionar o conteúdo retornado.
- Em caso de 403 tente instalar Playwright (`playwright install`) e execute de novo — o fallback usará um navegador headless.

### Boas práticas / Avisos ⚠️
- **Não compartilhe** nem comite sua chave OpenAI. Use variáveis de ambiente.
- Respeite os Termos de Uso dos sites que você raspa.
- Este sistema fornece **sugestões** com base em heurística/IA — **não há garantia de lucro**.

---

Se quiser, eu posso adicionar um `run.ps1` que automatiza a criação do venv, instalação das dependências e execução (deseja isso?).
