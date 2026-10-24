# Portal público: renderização e inspeção visual — entrega parcial

Data: 2026-10-23. Telas renderizadas localmente; servidor e deploy ainda pendentes.

## Implementação

- Home, catálogo, detalhe, estado vazio, página indisponível, Sobre e Contato renderizados em HTML pelo módulo `web/rendering.py`.
- Marca SVG, fonte Inter e imagem social copiadas sem alteração de `prospecTeam/public`. Paleta, bordas e linguagem visual preservadas. Não houve redesign da identidade.
- Formulários GET para busca/filtros, parâmetros compartilháveis, paginação, navegação por teclado e skip link. O backend ainda precisa servir os resultados das submissões.
- Conteúdo de vagas disponível no HTML inicial. JavaScript externo apenas recolhe filtros inicialmente em celulares; conteúdo e controles continuam presentes sem ele.
- Graduação/experiência desconhecidas permanecem distintas de dispensa. Aviso de elegibilidade não confirmada aparece antes do CTA, inclusive no celular.
- Candidatura suspensa não gera link `/go`; relação de indicação tem aviso perceptível quando presente no snapshot.
- Title, description, canonical, OG e noindex em resultados filtrados/retirados. Nenhum pré-carregamento do CTA.
- Conteúdo externo escapado; destino de fonte não aceita esquema JavaScript.
- E-mail `contato@buscadin.app` reaproveitado das páginas públicas atuais; funcionamento da caixa ainda não foi verificado.

## Evidências

- Suíte Python: **131 testes passando**.
- Inspeção Chromium via Playwright em 1440, 390 e 320 px, para home, catálogo e dois estados de detalhe: **12 combinações sem overflow horizontal**.
- Verificados carregamento da Inter local, abertura/fechamento nativo dos filtros, ordem aviso/CTA, skip link por teclado e presença dos conteúdos/formulários com JavaScript desativado.
- Contraste das amostras medidas (texto principal, metadados, elegibilidade, avisos, botão e fonte): mínimo **5,78:1**. Não equivale a auditoria WCAG completa.
- Todas as requisições do navegador interceptadas e respondidas com arquivos locais; nenhuma conexão ao site de produção. Dados de vagas são fictícios, isolados em `.preview/` ignorado pelo Git.

Reprodução:

```sh
uv run python scripts/preview_portal.py
node scripts/verify-portal.mjs /caminho/para/playwright/index.mjs
```

Screenshots e relatório JSON ficam em `.preview/portal/`. Playwright precisa estar disponível no ambiente de inspeção; não é dependência do portal em produção. O Chromium exigiu execução fora do sandbox, autorizada para esse comando.

## SEO: condição ainda pendente

A documentação oficial do Google exige que `JobPosting.description` represente a descrição completa e `datePosted` a data original do empregador. Portanto resumos editoriais não recebem essa marcação automaticamente. Falta implementar aprovação de completude/permissão, validação dos campos e geração condicional, além de respostas HTTP e sitemap efetivamente servidos.

Referência consultada em 2026-10-23: https://developers.google.com/search/docs/appearance/structured-data/job-posting

## Limites desta entrega

Ainda não há servidor HTTP nem verificação de formulário/redirecionamento ponta a ponta no navegador. Termos e privacidade precisam refletir a operação final; links de navegação estão previstos, mas essas páginas ainda não foram implementadas. Não houve migração real, auditoria de VPS, teste de carga, lançamento ou validação real de candidatura/Telegram.
