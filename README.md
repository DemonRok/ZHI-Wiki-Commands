# ZHI Wiki Commands

Questo repository genera documentazione (Markdown) dei comandi **player** presenti in `D:\GitHubZHI\poltest`, senza pubblicare il codice sorgente.

## Generazione

Requisiti: Python 3.

Esecuzione (da Windows):

```powershell
python .\tools\generate_wiki.py --poltest D:\GitHubZHI\poltest --out .\docs
```

Il comando crea/aggiorna:
- `docs/index.md`
- `docs/commands/*.md`

## Filtro “solo player”

Lo scanner legge `scripts\textcmd\player\*.src` e applica un filtro conservativo:
- include di default solo script “player puri”
- esclude script che contengono riferimenti staff (`CMDLEVEL_`, `IsStaff(`, `.cmdlevel`) a meno di override

Override:
- `config\include_mixed.txt` (una riga per comando, es. `all`)
- `config\exclude.txt` (una riga per comando, es. `debugtest`)
