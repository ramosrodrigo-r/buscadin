# Núcleo de publicação web — entrega parcial

Data: 2026-10-23. O portal e a integração de transporte ainda não estão entregues.

## Implementado localmente

- Política de destino HTTPS com domínio exato autorizado e preservação da URL de indicação.
- `SitePublicationService`: cada comando usa uma sessão própria e só retorna sucesso após commit.
- Prévia expira em 15 minutos, é vinculada ao administrador e guarda fingerprint de conteúdo, destino e versão.
- Confirmação revalida a vaga e indicação. Snapshot aprovado separado dos dados operacionais impede alterações públicas silenciosas na recoleta.
- Versão com comparação atômica, histórico de decisões e confirmação idempotente, inclusive callback simultâneo repetido.
- Despublicação manual com motivo e versão esperada.
- Destino revalidado na candidatura: não resolve um link substituto automaticamente. Indicação inválida ou URL alterada suspende CTA e grava alerta durável.
- Reconciliação em lotes permite detectar invalidação sem aguardar clique. Status operacional inativo/incompatível retira a publicação. O agendamento dessa rotina e o envio de alertas ainda precisam ser conectados ao runtime.
- Resumo editorial explícito para a prévia. Não copiar automaticamente a descrição integral da fonte para conteúdo público.

## Schema e compatibilidade

Migration `0004_site_publications` adiciona quatro tabelas: `site_publications`, `site_previews`, `site_publication_events`, `site_alerts`. Não copia estados editoriais antigos para publicação web. IDs de vagas e comandos existentes permanecem.

Campos de salário no ORM agora declaram `Float` explicitamente, correspondendo à migration original. A referência circular ao link resolvido recebe o nome já existente e `use_alter`, permitindo ordenar corretamente o schema. A comparação Alembic/modelos passa no banco SQLite temporário.

## Evidências

`uv run pytest -q`: 75 testes passaram, incluindo 16 cenários transacionais de publicação e teste real de Alembic/backup/restauração.

O teste de migration:

1. Cria banco temporário até 0003 e insere vaga legada com ID estável e estado editorial PUBLICADA.
2. Aplica 0004 e confirma zero publicações automáticas; executa `alembic check`.
3. Publica explicitamente pelo serviço, faz backup SQLite e reverte 0004 no banco isolado.
4. Confirma preservação da vaga e restaura o backup em outro arquivo.
5. Verifica integridade, publicação e evento histórico restaurados.

`git diff --check`: passou.

Esses testes não demonstram capacidade da VPS, concorrência PostgreSQL, backup externo criptografado ou entrega ponta a ponta pelo Telegram/site.

## Implantação e rollback

Nenhuma migration foi aplicada a dados reais. Antes de implantar: identificar VPS/banco, fazer backup externo, verificar restauração e aprovar o plano de substituição do portal com base no inventário.

Preferir rollback de código mantendo as tabelas aditivas. `downgrade` remove histórico de publicação; não executá-lo em produção sem backup/exportação e plano de preservação de decisões posteriores ao backup. O teste de downgrade prova o comportamento em ambiente descartável, não autoriza descarte de histórico real.

## Próximas integrações

- Escolha de backend/transportes e deploy após auditoria da VPS.
- Contrato privado autenticado, rotas públicas, limites e tratamento de erros.
- Comandos/botões Telegram para resumo, prévia, confirmação, atualização e retirada; envio/retry de `site_alerts`.
- Modelagem de empresas, requisitos e evidências; política de conteúdo e disclosure por programa.
- Home, catálogo, filtros, paginação, detalhe, SEO, cache/invalidação e candidatura.
- Verificação de encerramento na fonte, scheduler, migração PostgreSQL se selecionado, carga e operação.
