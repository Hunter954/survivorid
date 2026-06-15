# SurvivorID MVP

MVP em Python/Flask + PostgreSQL inspirado no layout aprovado: home com busca PUBG, perfil público de player, rankings, feed, medalhas, claim de perfil e painel admin para subir imagens.

## O que já vem pronto

- Home dark gamer com busca de jogador
- Página pública do player com stats, score, badges, gráfico, radar e partidas recentes
- Cadastro, login e logout
- Fluxo de reivindicação/claim do perfil
- Painel admin
- Upload de imagens gerais, hero, banners, avatares e medalhas
- CRUD básico de medalhas
- Configurações de texto da home
- Integração preparada com PUBG API via `PUBG_API_KEY`
- Modo demo para desenvolver sem chave da PUBG API
- PostgreSQL via `DATABASE_URL`
- Bootstrap + Bootstrap Icons + Chart.js

## Acesso admin inicial

Configure no Railway ou `.env`:

```env
ADMIN_EMAIL=admin@survivorid.local
ADMIN_PASSWORD=admin123
```

No primeiro boot, o app cria o admin automaticamente.

## Rodar local

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
cp .env.example .env
flask --app survivorid run --debug
```

No Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
flask --app survivorid run --debug
```

## Subir no Railway

1. Crie um repositório no GitHub e envie esses arquivos.
2. No Railway, crie um novo projeto a partir do GitHub.
3. Adicione um banco PostgreSQL.
4. Copie a variável `DATABASE_URL` do Postgres para o serviço web, se o Railway não injetar automaticamente.
5. Configure as variáveis:

```env
FLASK_SECRET_KEY=uma-chave-grande-aleatoria
PUBG_API_KEY=sua-chave-oficial-da-pubg
PUBG_DEFAULT_SHARD=steam
ADMIN_EMAIL=seu-email-admin
ADMIN_PASSWORD=sua-senha-forte
DEMO_MODE=true
```

6. Deploy. O `Procfile` já inicia com Gunicorn.

## PUBG API

O arquivo principal da integração está em:

```txt
survivorid/services/pubg_api.py
```

Com `DEMO_MODE=true`, se não houver `PUBG_API_KEY`, o sistema gera dados fake para você testar o fluxo inteiro.

Para produção, coloque a chave da PUBG API e depois expanda:

- `get_lifetime_stats()` para normalizar stats oficiais por modo/season;
- busca de matches recentes;
- download de telemetry;
- verificação real do claim por desafio;
- processamento de medalhas por evento.

## Imagens de armas, medalhas e ranking

Eu não incluí imagens oficiais retiradas do Google porque isso pode ter direitos autorais e não é seguro automatizar scraping. O painel admin já permite subir:

- medalhas;
- armas;
- banner da home;
- avatar/banner dos players;
- imagens de mapas/squads.

Caminho do admin:

```txt
/admin
/admin/assets
/admin/badges
/admin/settings
```

## Próximos passos recomendados

1. Criar worker com Bull/Redis ou APScheduler para sync automático.
2. Criar tabelas por stats de modo: solo, duo, squad, ranked.
3. Criar regras reais das medalhas em cima da telemetry.
4. Implementar ranking clean anti-bot.
5. Criar painel de times/squads.
6. Criar sistema de upload/seleção de assets por tipo: weapon, map, badge, hero.

## Railway build note

Este projeto inclui `mise.toml` com `python.github_attestations = false` para evitar falha recente do Railpack/mise ao instalar Python 3.12.4 quando o builder retorna `No GitHub artifact attestations found`.
