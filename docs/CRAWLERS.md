# Coleta manual nas empresas

No painel, abra **Fontes e coleta** e clique em **Buscar nas quatro empresas**
ou no botão de uma empresa. A execução continua se você sair dessa tela; ao
voltar, o painel mostra o progresso. Não existe agendamento para estes crawlers.
Eles não publicam, não se candidatam, não fazem login nem ativam referrals.

## Instalação

```sh
uv sync --frozen
uv run playwright install chromium
uv run buscadin-admin
```

No Linux, instale as bibliotecas do navegador com
`uv run playwright install --with-deps chromium`. A imagem Docker aceita
`--build-arg INSTALL_CRAWLER_BROWSER=true`. O painel continua sendo um serviço
privado; a topologia de acesso via SSH está documentada em `ADMIN.md`.

## Fontes verificadas em 27/10/2026

| Fonte | Listagem pública | Extração |
| --- | --- | --- |
| micro1 | https://www.micro1.ai/experts/opportunities | Scroll incremental, links `jobs.micro1.ai/post/<uuid>`, descrição JSON-LD renderizada |
| Turing | https://work.turing.com/jobs | Botão Load more roles, painéis de descrição `?jobId=<id>` |
| Mercor | https://work.mercor.com/explore | Paginação, links públicos SEO `/jobs/<listingId>/<slug>`, JSON-LD da descrição |
| Alignerr | https://www.alignerr.com/en/jobs | Load more roles, dados públicos incorporados em `__NEXT_DATA__` das páginas `/jobs/<uuid>` |

As consultas usam navegador sem sessão, com hosts de navegação fixos, verificação
de robots.txt, intervalo entre páginas e sem acesso direto a APIs privadas.
Login, CAPTCHA, bloqueios e alterações de layout não são contornados.
O fato de robots.txt permitir uma página não substitui os termos da fonte.

## Sem repetição

A identidade é `(source, source_job_id)`, protegida também por uma restrição única
no banco. Query strings de marketing são removidas. IDs já existentes são
ignorados independentemente da situação editorial: uma vaga descartada ou
retirada não volta como nova. Na persistência existe uma segunda checagem,
inclusive para duplicatas recebidas na própria rodada.

Vagas existentes não são atualizadas por esses crawlers — nem título, descrição,
links, requisitos ou decisões editoriais. Não há expiração automática baseada
na ausência em uma coleta parcial. Vagas novas podem entrar como excluídas do
Brasil ou elegibilidade desconhecida para revisão; não se promete que todos os
anúncios dessas empresas aceitem brasileiros. Português não prova localização.

Foi observado na Alignerr um anúncio com `countryCode=BR` e
`location=United States`. Essa contradição fica descrita na vaga para revisão e
não confirma elegibilidade para o Brasil. Requisitos não são presumidos.

## Limites e recuperação

- Até 5 lotes/páginas e 30 anúncios novos por empresa por execução.
- Dez minutos máximos por fonte; uma empresa falhar não impede as demais.
- O relatório distingue novos, conhecidos, falhas e limite de cobertura.
- A listagem começa novamente pelas vagas iniciais; não há varredura integral
  garantida nem cursor persistente para catálogos muito grandes nesta versão.
- Uma execução por processo administrativo; opere uma única instância do painel.
- Estado salvo em `bot_state`; decisões da rodada registradas em `audit_events`.
- Reiniciar o serviço interrompe a tarefa e informa interrupção ao reabrir.
  Vagas de fontes já concluídas permanecem salvas; repetir é seguro.
- Resultados de cada fonte são salvos transacionalmente ao terminar essa fonte.
  Não existem alterações no domínio público durante a coleta.

`POST /api/crawl` aceita `source: all|micro1|turing|mercor|alignerr`, exige a sessão
administrativa, origem e CSRF. `GET /api/crawl` retorna o progresso autenticado.
Não é preciso manter a conexão HTTP aberta durante a execução.

## Validação

Testes offline: `uv run pytest tests/test_company_crawler.py tests/test_admin.py`.
Incluem IDs canônicos, robots, dados conflitantes, falhas isoladas, execução
manual, concorrência de cliques, autenticação e duas rodadas sem duplicação ou
alteração das decisões do curador.

Diagnóstico real limitado, sem gravar no banco:

```sh
uv run python scripts/check_company_sources.py --source all --limit 1
```

O diagnóstico informa IDs, títulos, tamanho da descrição e elegibilidade, sem
imprimir descrições completas. A suíte automatizada usa fixtures; não depende
da disponibilidade das empresas. O teste de navegador do painel simula o
resultado de coleta para validar botões, relatório e comportamento responsivo.
