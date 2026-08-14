# Breaking Changes

## v0.1.7 -> v0.2.0

Instead of mounting a single `config.env` file volume in the Docker container a whole `/config` directory is now required. The `config.env` should still exist in it but now the logs will also be stored and rotated in the `/config/log` dir.

### Required updates
Create a new directory and add your `config.env` there. Mount that path to the `/config` dir.

```diff
- /path/to/config.env:/config.env
+ /path/to/config:/config
```