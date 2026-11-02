# Recheck das quatro fontes — 2026-11-02

Executado na VPS, com o runtime real do admin. Imagem final:
`buscadin-catalogue:d7184b3`. O painel respondeu HTTP 200 após o deploy.

## Resultado

| Fonte | Coleta pública | Links em sessão nova |
|---|---|---|
| micro1 | A listagem não carregou. `jobs.micro1.ai/robots.txt` respondeu 403 e o preflight OPTIONS da API de vagas também respondeu 403 nesta VPS. | Sem validação de vaga individual nesta rodada. |
| Turing | Três anúncios com descrição completa. | Três vagas salvas, seis aberturas finais corretas. |
| Mercor | Três anúncios com descrição completa. | Três vagas recém-coletadas, seis aberturas corretas. |
| Alignerr | Três anúncios com descrição completa. | Três vagas recém-coletadas, seis aberturas corretas. |

As aberturas usaram contextos novos do Chromium em 1280 × 900 e 390 × 900.
Foram confirmados título visível, identidade da vaga preservada na navegação e
presença da descrição. A amostra total foi de nove links e 18 aberturas finais.
A coleta diagnóstica teve limite de três vagas e duas páginas por fonte.

## Correção encontrada durante o recheck

A busca da Turing retornava zero resultados para o título completo
`Personal Account Generalist Raters (Android Smartphone Users)`. A busca pelo
título-base retornou três vagas; o `jobId=115452` abriu a vaga Android correta.

O gerador de links agora retira o complemento final entre parênteses somente do
parâmetro de busca. O título exibido e a identidade numérica continuam completos.
A correção foi validada no desktop e no celular e publicada em `d7184b3`.
Quatro registros existentes tiveram os links reparados, com eventos de auditoria.
Uma segunda execução do reparo encontrou zero alterações pendentes.

Os testes direcionados de crawler e coleta passaram: **31 testes**.

## Amostras

- Turing: `115452`, `117620`, `116917` (Clinical & Health Specialist).
- Mercor: `list_AAABoZp0wzuyh1qXnV5ADJMG`, `list_AAABoZQFI1_FwyFlEzJGgZW-`, `list_AAABoY6KV-qA2S205AlLgrqM`.
- Alignerr: `f1e68ec7-e0f2-40b3-a105-0d87f5724969`, `7b1a6994-7503-4bd6-b374-500c1a91850d`, `eabe7d69-748f-4b49-b36b-62129a2fb06f`.

Os resultados das coletas diagnósticas não foram inseridos no banco. A única
escrita nos registros de vagas foi o reparo auditado dos quatro links da Turing.
A micro1 permanece indisponível para coleta a partir desta VPS.
