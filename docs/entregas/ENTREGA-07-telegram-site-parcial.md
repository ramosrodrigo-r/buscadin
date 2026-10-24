# Telegram e contrato privado de publicação — entrega parcial

Data: 2026-10-23. Servidor HTTP e portal ainda pendentes.

## Implementação

- Cliente HTTP privado com Bearer e identidade Telegram, timeout, rejeição de redirects e mensagens de erro sem corpo remoto/credenciais.
- Integração opcional por `SITE_API_URL` e `SITE_API_TOKEN`; ambos os IDs de administrador são exigidos. Sem essas variáveis, o bot legado continua funcionando.
- `/publicar_site` e `/atualizar_site` recebem destino escolhido, solicitam resumo editorial e apresentam prévia completa com CTA de confirmação. A ausência de confirmação não publica.
- `/site`, `/despublicar_site`, `/pendentes_site` e `/publicadas_site` consultam a API privada.
- Retirada também pede confirmação e usa versão esperada. Repetição de callback antigo consulta estado atual para não anunciar como pública uma vaga já retirada.
- Resumos longos são escapados e divididos por tamanho, sem cortar entidades HTML ou omitir partes da prévia.
- `/cancelar` encerra o fluxo de resumo; iniciar vínculo de indicação encerra o fluxo concorrente de resumo.
- Poller persiste cada update concluído, ignora reentregas antigas e não perde todo o avanço do lote por falha posterior.
- Loop principal tenta novamente após erro de polling, sem registrar a URL do token em exceções.

## Contrato

`docs/api/publication.openapi.json` define os endpoints consumidos pelo cliente, schemas, autenticação e respostas de conflito. Esse contrato cobre publicação; ingestão, links e API pública continuam pendentes.

O bot não escreve tabelas da plataforma. Os testes de fluxo usam um adaptador local conectado ao serviço transacional real, com bancos separados para bot e plataforma. O servidor HTTP ainda precisa implementar o contrato e ligar autenticação, limites e ingestão.

## Validação

`uv run pytest -q`: 97 testes passaram.

Cobertura adicional: identidades distintas, ausência do user ID, prévia sem publicação, HTML e resumos longos, resposta perdida após commit, reentrega sem duplicação, retirada confirmada, estado atual após callback antigo, erros HTTP, redirects e avanço durável do polling.

Não houve chamadas a Telegram ou servidor reais, deploy nem acesso à VPS. A auditoria de infraestrutura continua pendente de identificação/acesso do servidor. Não habilitar o cliente contra endpoint inexistente.
