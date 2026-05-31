# PostgreSQL Schema Report — SyncDesk

## Tabelas

### users

* Domínio: `auth`
* Descrição: usuários do sistema, com credenciais locais/OAuth, flags de estado, vínculo opcional com empresa e avatar.
* Primary Key: `id`
* Columns:
  * `id`: `UUID`, not null, PK, default Python `uuid4`
  * `email`: `String(255)`, not null, unique via índice `ix_users_email`
  * `username`: `String(50)`, nullable, unique constraint `uq_users_username`
  * `name`: `String(50)`, nullable
  * `password_hash`: `String(255)`, nullable
  * `oauth_provider`: enum PostgreSQL `oauth_provider` (`local`, `google`, `microsoft`), nullable
  * `oauth_provider_id`: `String(255)`, nullable, unique constraint `uq_users_oauth_provider_id`
  * `company_id`: `UUID`, nullable, FK para `companies.id`, indexado
  * `avatar_file_id`: `UUID`, nullable, FK para `file_objects.id`
  * `is_active`: `Boolean`, not null, default Python `True`, indexado
  * `is_verified`: `Boolean`, not null, default Python `False`, indexado
  * `must_change_password`: `Boolean`, not null, default Python `False`
  * `must_accept_terms`: `Boolean`, not null, default Python `False`
  * `created_at`: `DateTime`, not null, server default `now()`
  * `updated_at`: `DateTime`, nullable
  * `deleted_at`: `DateTime`, nullable
* Foreign Keys:
  * `company_id -> companies.id`
  * `avatar_file_id -> file_objects.id`
* Indexes:
  * `ix_users_email`, unique
  * `ix_users_is_active`
  * `ix_users_is_verified`
  * `ix_users_company_id`
* Constraints:
  * PK `pk_users`
  * unique `uq_users_username`
  * unique `uq_users_oauth_provider_id`
  * FK `fk_users_company_id_companies`
  * FK `fk_users_avatar_file_id_file_objects`
* Relationships:
  * `users 1:N sessions`
  * `users N:N roles via user_roles`
  * `users N:N levels via user_levels`
  * `companies 1:N users`
  * `file_objects 1:N users` como avatar, pelo FK `users.avatar_file_id`; o model não declara `relationship`
* Notes:
  * `email` é único por índice, não por `UniqueConstraint` explícito na migration.
  * `avatar_file_id` não possui índice explícito.
  * Soft delete lógico via `deleted_at`.

### roles

* Domínio: `auth`
* Descrição: perfis/papéis de autorização.
* Primary Key: `id`
* Columns:
  * `id`: `Integer`, not null, PK
  * `name`: `String(30)`, not null, unique
  * `description`: `String(255)`, nullable
  * `created_at`: `DateTime`, not null, server default `now()`
* Foreign Keys: nenhum
* Indexes: nenhum explícito além da constraint unique
* Constraints:
  * PK `pk_roles`
  * unique `uq_roles_name`
* Relationships:
  * `roles N:N users via user_roles`
  * `roles N:N permissions via role_permissions`
* Notes:
  * Seed cria roles: `admin`, `user`, `agent`, `client`.

### permissions

* Domínio: `auth`
* Descrição: permissões granulares usadas por roles.
* Primary Key: `id`
* Columns:
  * `id`: `Integer`, not null, PK
  * `name`: `String(50)`, not null, unique
  * `description`: `String(255)`, nullable
  * `created_at`: `DateTime`, not null, server default `now()`
* Foreign Keys: nenhum
* Indexes: nenhum explícito além da constraint unique
* Constraints:
  * PK `pk_permissions`
  * unique `uq_permissions_name`
* Relationships:
  * `permissions N:N roles via role_permissions`
* Notes:
  * Seed popula permissões de usuários, roles, permissões, sessões, chat, tickets, empresas e produtos.

### user_roles

* Domínio: `auth`
* Descrição: tabela associativa entre usuários e roles.
* Primary Key: composta por `user_id`, `role_id`
* Columns:
  * `user_id`: `UUID`, not null, PK, FK para `users.id`
  * `role_id`: `Integer`, not null, PK, FK para `roles.id`
  * `created_at`: `DateTime`, not null, server default `now()`
* Foreign Keys:
  * `user_id -> users.id`
  * `role_id -> roles.id`
* Indexes:
  * nenhum índice separado; a PK composta indexa `(user_id, role_id)`
* Constraints:
  * PK `pk_user_roles`
  * FK `fk_user_roles_user_id_users`
  * FK `fk_user_roles_role_id_roles`
* Relationships:
  * `users N:N roles via user_roles`
* Notes:
  * Impede duplicidade do par `(user_id, role_id)` pela PK composta.
  * Não há `ondelete` definido.

### role_permissions

* Domínio: `auth`
* Descrição: tabela associativa entre roles e permissões.
* Primary Key: composta por `role_id`, `permission_id`
* Columns:
  * `role_id`: `Integer`, not null, PK, FK para `roles.id`
  * `permission_id`: `Integer`, not null, PK, FK para `permissions.id`
  * `created_at`: `DateTime`, not null, server default `now()`
* Foreign Keys:
  * `role_id -> roles.id`
  * `permission_id -> permissions.id`
* Indexes:
  * nenhum índice separado; a PK composta indexa `(role_id, permission_id)`
* Constraints:
  * PK `pk_role_permissions`
  * FK `fk_role_permissions_role_id_roles`
  * FK `fk_role_permissions_permission_id_permissions`
* Relationships:
  * `roles N:N permissions via role_permissions`
* Notes:
  * Impede duplicidade do par `(role_id, permission_id)` pela PK composta.
  * Não há `ondelete` definido.

### sessions

* Domínio: `auth`
* Descrição: sessões/autenticação por refresh token.
* Primary Key: `id`
* Columns:
  * `id`: `UUID`, not null, PK, default Python `uuid4`
  * `refresh_token_hash`: `String(255)`, not null, unique, indexado
  * `status`: enum PostgreSQL `session_status` (`active`, `expired`, `invalid`, `revoked`), not null, default Python `SessionStatus.ACTIVE`
  * `device_info`: `JSONB`, not null, default Python `dict`
  * `expires_at`: `DateTime`, not null
  * `last_used_at`: `DateTime`, nullable
  * `created_at`: `DateTime`, not null, server default `now()`
  * `updated_at`: `DateTime`, nullable
  * `revoked_at`: `DateTime`, nullable
  * `user_id`: `UUID`, not null, FK para `users.id`, indexado
* Foreign Keys:
  * `user_id -> users.id`
* Indexes:
  * `idx_sessions_user_id_status` em `(user_id, status)`
  * `ix_sessions_refresh_token_hash`, unique
  * `ix_sessions_user_id`
* Constraints:
  * PK `pk_sessions`
  * FK `fk_sessions_user_id_users`
* Relationships:
  * `users 1:N sessions`
* Notes:
  * O relacionamento no model usa cascade ORM `all, delete-orphan`, mas isso não é `ON DELETE CASCADE` no banco.
  * Não há `ondelete` definido na FK.

### password_reset_tokens

* Domínio: `auth`
* Descrição: tokens de reset de senha e convite.
* Primary Key: `id`
* Columns:
  * `id`: `UUID`, not null, PK, default Python `uuid4`
  * `user_id`: `UUID`, not null, FK para `users.id`, indexado
  * `token_hash`: `String(255)`, not null, unique, indexado
  * `purpose`: enum PostgreSQL `token_purpose` (`reset`, `invite`), not null
  * `created_at`: `DateTime`, not null, server default `now()`
  * `expires_at`: `DateTime`, not null
  * `used_at`: `DateTime`, nullable
* Foreign Keys:
  * `user_id -> users.id`
* Indexes:
  * `ix_password_reset_tokens_user_id`
  * `ix_password_reset_tokens_token_hash`, unique
* Constraints:
  * PK `pk_password_reset_tokens`
  * FK `fk_password_reset_tokens_user_id_users`
* Relationships:
  * `users 1:N password_reset_tokens`
* Notes:
  * O model não declara `relationship` ORM com `User`, mas há FK explícita.

### user_terms_acceptances

* Domínio: `auth`
* Descrição: aceite de termos por usuário e versão dos termos.
* Primary Key: `id`
* Columns:
  * `id`: `UUID`, not null, PK, default Python `uuid4`
  * `user_id`: `UUID`, not null, FK para `users.id`, indexado
  * `terms_version`: `String(16)`, not null, indexado
  * `accepted_at`: `DateTime`, not null
* Foreign Keys:
  * `user_id -> users.id`
* Indexes:
  * `ix_user_terms_acceptances_user_id`
  * `ix_user_terms_acceptances_terms_version`
* Constraints:
  * PK `pk_user_terms_acceptances`
  * FK `fk_user_terms_acceptances_user_id_users`
* Relationships:
  * `users 1:N user_terms_acceptances`
* Notes:
  * Não há unique para impedir múltiplos aceites do mesmo usuário na mesma versão.

### levels

* Domínio: `auth`
* Descrição: níveis de atendimento/suporte, como `N1`, `N2`, `N3`.
* Primary Key: `id`
* Columns:
  * `id`: `Integer`, not null, PK
  * `name`: `String(10)`, not null, unique
* Foreign Keys: nenhum
* Indexes: nenhum explícito além da constraint unique
* Constraints:
  * PK `pk_levels`
  * unique `uq_levels_name`
* Relationships:
  * `levels N:N users via user_levels`
* Notes:
  * Seed cria `N1`, `N2`, `N3`.

### user_levels

* Domínio: `auth`
* Descrição: tabela associativa entre usuários/agentes e níveis de atendimento.
* Primary Key: composta por `user_id`, `level_id`
* Columns:
  * `user_id`: `UUID`, not null, PK, FK para `users.id`
  * `level_id`: `Integer`, not null, PK, FK para `levels.id`
  * `created_at`: `DateTime`, not null, server default `now()`
* Foreign Keys:
  * `user_id -> users.id`, `ON DELETE CASCADE`
  * `level_id -> levels.id`, `ON DELETE CASCADE`
* Indexes:
  * nenhum índice separado; a PK composta indexa `(user_id, level_id)`
* Constraints:
  * PK `pk_user_levels`
  * FK `fk_user_levels_user_id_users`
  * FK `fk_user_levels_level_id_levels`
* Relationships:
  * `users N:N levels via user_levels`
* Notes:
  * Impede duplicidade do par `(user_id, level_id)` pela PK composta.
  * Ao deletar usuário ou level no banco, o vínculo é removido por cascade.

### companies

* Domínio: `companies`
* Descrição: empresas/clientes cadastradas no sistema.
* Primary Key: `id`
* Columns:
  * `id`: `UUID`, not null, PK, default Python `uuid4`
  * `legal_name`: `String(255)`, not null, unique via índice `ix_companies_legal_name`
  * `trade_name`: `String(255)`, nullable, indexado
  * `tax_id`: `String(14)`, not null, unique via índice `ix_companies_tax_id`
  * `created_at`: `DateTime`, not null, server default `now()`
  * `deleted_at`: `DateTime`, nullable
* Foreign Keys: nenhum
* Indexes:
  * `ix_companies_legal_name`, unique
  * `ix_companies_tax_id`, unique
  * `ix_companies_trade_name`
* Constraints:
  * PK `pk_companies`
* Relationships:
  * `companies 1:N users`
  * `companies N:N products via company_products`
* Notes:
  * Soft delete lógico via `deleted_at`.
  * `legal_name` e `tax_id` são únicos por índice, não por `UniqueConstraint` explícito.

### products

* Domínio: `products`
* Descrição: produtos disponíveis/contratáveis por empresas.
* Primary Key: `id`
* Columns:
  * `id`: `Integer`, not null, PK
  * `name`: `String(127)`, not null
  * `description`: `String(500)`, nullable
  * `created_at`: `DateTime`, not null, server default `now()`
  * `deleted_at`: `DateTime`, nullable
* Foreign Keys: nenhum
* Indexes: nenhum explícito
* Constraints:
  * PK `pk_products`
* Relationships:
  * `products N:N companies via company_products`
* Notes:
  * Soft delete lógico via `deleted_at`.
  * Não há unique em `name` no model/migration, apesar de o repositório tratar `IntegrityError` como conflito de produto.

### company_products

* Domínio: `companies` / `products`
* Descrição: tabela associativa de produtos contratados por empresas, com datas de compra e suporte.
* Primary Key: composta por `company_id`, `product_id`
* Columns:
  * `company_id`: `UUID`, not null, PK, FK para `companies.id`
  * `product_id`: `Integer`, not null, PK, FK para `products.id`
  * `bought_at`: `DateTime`, not null, server default `now()`
  * `support_until`: `DateTime`, not null
* Foreign Keys:
  * `company_id -> companies.id`
  * `product_id -> products.id`
* Indexes:
  * nenhum índice separado; a PK composta indexa `(company_id, product_id)`
* Constraints:
  * PK `pk_company_products`
  * FK `fk_company_products_company_id_companies`
  * FK `fk_company_products_product_id_products`
* Relationships:
  * `companies N:N products via company_products`
* Notes:
  * Impede duplicidade do par `(company_id, product_id)` pela PK composta.
  * Não há `ondelete` definido.
  * A cardinalidade resultante é: uma empresa pode ter muitos produtos, um produto pode pertencer a muitas empresas.

### file_objects

* Domínio: `files`
* Descrição: metadados de arquivos armazenados externamente, como anexos de chat e avatares.
* Primary Key: `id`
* Columns:
  * `id`: `UUID`, not null, PK, default Python `uuid4`
  * `bucket`: `String(63)`, not null
  * `object_key`: `Text`, not null
  * `original_filename`: `String(255)`, not null
  * `content_type`: `String(127)`, not null
  * `size_bytes`: `BigInteger`, not null
  * `context`: enum PostgreSQL `file_context` (`live_chat_message`, `user_avatar`), not null, indexado
  * `status`: enum PostgreSQL `file_status` (`pending`, `uploaded`, `failed`, `deleted`), not null, default Python `FileStatus.PENDING`, indexado
  * `uploaded_by_user_id`: `UUID`, not null, FK para `users.id`, indexado
  * `checksum_sha256`: `String(64)`, nullable
  * `created_at`: `DateTime(timezone=True)`, not null, server default `now()`
  * `uploaded_at`: `DateTime(timezone=True)`, nullable
  * `deleted_at`: `DateTime(timezone=True)`, nullable
  * `purged_at`: `DateTime(timezone=True)`, nullable
* Foreign Keys:
  * `uploaded_by_user_id -> users.id`
* Indexes:
  * `ix_file_objects_context`
  * `ix_file_objects_status`
  * `ix_file_objects_uploaded_by_user_id`
  * `ix_file_objects_status_created_at` em `(status, created_at)`
  * `ix_file_objects_context_uploaded_at` em `(context, uploaded_at)`
  * `ix_file_objects_status_deleted_at` em `(status, deleted_at)`
* Constraints:
  * PK `pk_file_objects`
  * FK `fk_file_objects_uploaded_by_user_id_users`
* Relationships:
  * `users 1:N file_objects` como usuário que fez upload
  * `file_objects 1:N users` para avatares via `users.avatar_file_id`
* Notes:
  * A migration `a6e80aba25a6` criou `uq_file_objects_object_key`, mas a migration `cca8b6c18070` removeu essa unique constraint. O estado final atual é **sem unique em `object_key`**.
  * Soft delete lógico por `status = deleted` e `deleted_at`.
  * `purged_at` marca remoção física posterior do storage.

### email_outbox

* Domínio: `notifications`
* Descrição: fila transacional/outbox para envio de e-mails.
* Primary Key: `id`
* Columns:
  * `id`: `UUID`, not null, PK, default Python `uuid4`
  * `event_type`: `String(64)`, not null
  * `recipient`: `String(320)`, not null
  * `payload`: `JSONB`, not null
  * `status`: enum PostgreSQL `email_outbox_status` (`PENDING`, `PROCESSING`, `SENT`, `RETRY`, `DEAD`), not null, default Python `EmailOutboxStatus.PENDING`
  * `attempts`: `Integer`, not null, default Python `0`
  * `max_attempts`: `Integer`, not null, default Python `5`
  * `last_error`: `Text`, nullable
  * `next_attempt_at`: `DateTime`, not null, server default `now()`
  * `created_at`: `DateTime`, not null, server default `now()`
  * `updated_at`: `DateTime`, not null, server default `now()`, Python/onupdate `func.now()`
  * `sent_at`: `DateTime`, nullable
  * `locked_at`: `DateTime`, nullable
  * `lock_owner`: `String(128)`, nullable
* Foreign Keys: nenhum
* Indexes:
  * `ix_email_outbox_status_next_attempt_at` em `(status, next_attempt_at)`
  * `ix_email_outbox_event_type`
  * `ix_email_outbox_recipient`
* Constraints:
  * PK `pk_email_outbox`
* Relationships:
  * nenhuma FK explícita
* Notes:
  * Tabela isolada de infraestrutura/eventos.
  * `event_type` é string, não FK para outra tabela.

---

## Tabelas Associativas

### user_roles

* Relaciona: `users` e `roles`
* PK composta: sim, `(user_id, role_id)`
* Impede duplicidade: sim
* Cardinalidade resultante: `users N:N roles`
* `ondelete`: não definido

### role_permissions

* Relaciona: `roles` e `permissions`
* PK composta: sim, `(role_id, permission_id)`
* Impede duplicidade: sim
* Cardinalidade resultante: `roles N:N permissions`
* `ondelete`: não definido

### user_levels

* Relaciona: `users` e `levels`
* PK composta: sim, `(user_id, level_id)`
* Impede duplicidade: sim
* Cardinalidade resultante: `users N:N levels`
* `ondelete`: `CASCADE` em ambos os FKs

### company_products

* Relaciona: `companies` e `products`
* PK composta: sim, `(company_id, product_id)`
* Impede duplicidade: sim
* Cardinalidade resultante: `companies N:N products`
* `ondelete`: não definido
* Campos extras: `bought_at`, `support_until`

---

## Relacionamentos Principais

* `companies 1:N users`
* `users 1:N sessions`
* `users 1:N password_reset_tokens`
* `users 1:N user_terms_acceptances`
* `users 1:N file_objects` via `file_objects.uploaded_by_user_id`
* `file_objects 1:N users` via `users.avatar_file_id`
* `users N:N roles via user_roles`
* `roles N:N permissions via role_permissions`
* `users N:N levels via user_levels`
* `companies N:N products via company_products`

Relações lógicas sem FK PostgreSQL:

* `tickets` e `attendances` existem como documentos MongoDB/Beanie, não como tabelas PostgreSQL.
* Permissões de `chat`, `ticket`, `company`, `product` existem como strings em `permissions.name`, mas não há FKs para entidades desses domínios.