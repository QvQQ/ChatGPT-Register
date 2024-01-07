# `refresh_tokens_cli`

**Usage**:

```console
$ refresh_tokens_cli [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

**Commands**:

* `assemble`: Assemble pool token
* `obtain`: Obtain new session tokens if not exists.
* `refresh`: Refresh tokens.

## `refresh_tokens_cli assemble`

Assemble pool token

**Usage**:

```console
$ refresh_tokens_cli assemble [OPTIONS]
```

**Options**:

* `--count INTEGER`: Number of accounts to process  [default: 100]
* `--help`: Show this message and exit.

## `refresh_tokens_cli obtain`

Obtain new session tokens if not exists.

**Usage**:

```console
$ refresh_tokens_cli obtain [OPTIONS]
```

**Options**:

* `--count INTEGER`: Number of accounts to process  [default: 10]
* `--help`: Show this message and exit.

## `refresh_tokens_cli refresh`

Refresh tokens.

**Usage**:

```console
$ refresh_tokens_cli refresh [OPTIONS]
```

**Options**:

* `--empty-tokens / --no-empty-tokens`: Refresh tokens only if share or access token is empty  [default: no-empty-tokens]
* `--count INTEGER`: Number of accounts to process  [default: -1]
* `--help`: Show this message and exit.
