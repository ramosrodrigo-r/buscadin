# Consulta pública e requisitos explícitos — entrega parcial

Data: 2026-10-23. Camada de domínio concluída localmente; endpoints e telas ainda pendentes.

## Comportamento implementado

- `PublicCatalogue` consulta exclusivamente snapshots aprovados e vagas operacionalmente ativas/elegíveis. Não lê título, empresa ou resumo atualizados pela coleta como conteúdo público sem nova aprovação.
- Busca normalizada por cargo, empresa e resumo, incluindo remoção de acentos para pesquisa. Caracteres `%` e `_` não são tratados como curingas fornecidos pelo usuário.
- Filtros por categoria, idioma explicitamente informado, país, elegibilidade Brasil, remuneração divulgada e graduação/experiência. Paginação limitada a 50 registros por requisição; recência com desempate por ID.
- Graduação e experiência têm três estados: `unknown`, `required`, `not_required`. Afirmações exigem evidência não vazia; ausência vira `unknown`.
- Os estados seguem para a prévia Telegram e o snapshot público. Evidências ficam no registro privado da decisão, participando da detecção de mudanças após prévia.
- URLs de detalhe usam slug preservado após a primeira publicação, mesmo quando um novo título é aprovado.
- Consulta individual revalida candidatura; sitemap é consultado em lotes e exclui vagas invisíveis.
- Projeção pública usa lista explícita de campos, sem serializar ORM, URL privada de indicação, ator, comissão ou notas internas. O detalhe pode mostrar somente o hostname do destino.
- Relação de indicação inclui aviso público simples no snapshot e na prévia. Regras específicas dos programas ainda precisam ser conferidas antes de uso real.
- Se a fonte retirar a confirmação de Brasil, a vaga anteriormente confirmada some das consultas públicas imediatamente e a reconciliação registra a retirada.

## Requisitos: limite atual

O modelo recebe fatos estruturados e evidência. Não há inferência por nome do cargo, descrição em português ou localização Brasil. O conector Himalayas atual ainda não fornece requisitos estruturados; nesses casos os campos permanecem desconhecidos. A edição administrativa desses fatos na API/Telegram está pendente.

## Migração e testes

Migration 0005 adiciona requisitos às vagas e texto de busca às publicações. Preenche o índice textual de snapshots existentes sem alterar seu conteúdo aprovado ou seu estado.

Suíte completa: **123 testes passando**. Inclui filtros combinados, idiomas múltiplos, pesquisa com acentos, limites de paginação, requisitos ausentes versus dispensados, isolamento de dados privados, retirada/inatividade, perda de confirmação Brasil, estabilidade de URL e invalidação de prévia quando a evidência muda.

O teste real de Alembic foi estendido para aplicar a cadeia completa a dados legados, comparar modelos/schema e verificar restauração em arquivo isolado. Nenhuma migration foi aplicada em produção. Consultas e migrations ainda precisam de execução em PostgreSQL caso esse banco seja escolhido para implantação.

## Próximas entregas

Implementar endpoints privados/públicos e as telas de home, catálogo e detalhe; edição de requisitos; ingestão e gestão de links via contrato central; scheduler e envio de alertas; validação visual, operacional e de infraestrutura. A decisão final de implantação permanece condicionada ao inventário da VPS.
