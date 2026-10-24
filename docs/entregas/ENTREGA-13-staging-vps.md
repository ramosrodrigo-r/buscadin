# Entrega 13 — staging interno na VPS

Data: 2026-10-24.

Foi criado um ambiente de catálogo isolado no Docker Swarm da VPS. Nenhum
serviço legado, Listmonk, domínio ou porta pública foi alterado.

## Componentes criados

- `buscadin-catalogue-db-stage`: PostgreSQL 18 próprio, com volume
  `buscadin-catalogue-stage-data` em `/var/lib/postgresql`.
- `buscadin-catalogue-migrate-stage`: job concluído que aplicou migrations
  0001 a 0005.
- `buscadin-catalogue-portal-stage`: portal em rede `dokploy-network`, sem
  porta publicada.

As credenciais do banco e da API interna foram geradas na VPS e armazenadas
como Docker Secrets. Elas não foram impressas, gravadas no repositório ou
reutilizadas dos serviços legados. O staging usa identificação administrativa
fictícia e não executa o bot ou envia mensagens ao Telegram.

## Evidência

O job de migration terminou como `Complete`. O portal estava `Running` e o
healthcheck chamado de dentro do próprio container retornou:

```json
{"status":"ok"}
```

## Limites e próxima etapa

O ambiente ainda não é um serviço administrado pela interface do Dokploy nem
tem URL pública. A imagem `buscadin-catalogue:cdbe23c` foi construída na VPS a
partir do commit local porque a máquina atual não possui credencial GitHub
para publicar os commits no repositório remoto.

Antes de abrir staging/publicação: configurar origem Git ou registry para
imagens versionadas, rotacionar os segredos expostos dos serviços legados,
definir backup externo criptografado, usar o ID real do administrador e
executar o fluxo Telegram com uma vaga sintética.
