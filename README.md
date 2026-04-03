# NextUp
NextUp is a program that allows [Jellyfin](https://jellyfin.org/) admins to generate user personalized movie and series recommendations directly in Jellyfin regardless of client using Jellyfin libraries. User are also able to generate media requests in [Seer](https://seerr.dev/) right from the Jellyfin UI by favoriting the media in their recommendations.

NextUp is also compatible with [WatchState](https://github.com/arabcoders/watchstate) to allow for more long live watch history to improve recommendations and avoid getting recommendations for media the user has already watched but might have been removed from the server.

## Features
- Support for any number of users
- Optional WatchState integration for long lived watch history
- Optional Seerr integration to generate requests from Jellyfin UI

## How It Works
NextUp looks at a user's movie and series watch history and uses that to query [TMDB](https://www.themoviedb.org/?language=en-US) for recommendations based on that watched piece of media. It then creates a minimal `metadata.json` file and saves it in a directory specific for that user in a place that Jellyfin can import along with a dummy video file. Jellyfin admins then create a library for that user's recommendations and allow then allow that user to see that library. 

If the Seerr integration is enabled in NextUp users can favorite media from their recommendations to automatically request it for download in Seerr. Note that due to the way Seerr's api is implemented [all requests are auto-approved](https://github.com/seerr-team/seerr/issues/2678#issuecomment-4038790777).

### Watch History Limitation
Jellyfin's API only returns watch history for media currently on the server therefore users with a small changing library would not get the benefit of a long standing watch history to pull recommendations from.

[WatchState](https://github.com/arabcoders/watchstate) is a self-hostable tool that was originally designed to 
> sync your backends users play state without relying on third party services

However it also stores watch history for all media a user has watched regardless of the status on the media on the server. Using WatchState's API NextUp can fetch a complete watch history. WatchState stores actual watch history AND user-marked watched media. As a result users can "Mark as Watched" media in their recommendations to avoid recommending it in the future as well as use it as a seed for further recommendations.

## Installation / Usage
The easiest way to use NextUp is to use the Docker image but you can also build from source or run using Python directly.

### Docker

To allow NextUp to create recommendation files you must provide a directory as a volume mapped to `/recommendations`. Ensure the user used for the container has read _and_ write permissions to the recommendations directory.
Additionally, you must provide a config file mapped to `/config.env`. Check the [config.env.sample](config.env.sample) as a starting point.

The NextUp image defaults to port 5777 but accepts `APP_PORT` and `APP_HOST` to customize these values.

#### Compose
```yaml, compose.yaml
services:
  server:
    container_name: NextUp
    image: ghcr.io/20bbrown14/nextup:latest
    ports:
      - 5777:5777
    env_file: config.env
    user: "1000:1000"
    environment:
      - APP_HOST=0.0.0.0
      - APP_PORT=5777
    volumes:
      - /path/to/recommendations:/recommendations
      - /path/to/config/config.env:/config.env
```

#### Run
```sh
docker run -d \
  --name NextUp \
  --user "1000:1000" \
  -p 5777:5777 \
  --env-file config.env \
  -e APP_HOST=0.0.0.0 \
  -e APP_PORT=5777 \
  -v /path/to/recommendations:/recommendations \
  -v /path/to/config/config.env:/config.env \
  ghcr.io/20bbrown14/nextup:latest
```

#### Build from source
First clone the repository
`git clone https://github.com/20BBrown14/NextUp`

`cd` into the directory: `cd NextUp`

Add a new `compose.yaml` file which will be used to build and run the image
```yaml, compose.yaml
services:
  server:
    build:
      context: .
    ports:
      - 5777:5777
    env_file: config.env
    user: "1000:1000"
    environment:
      - APP_HOST=0.0.0.0
      - APP_PORT=5777
    volumes:
      - /path/to/recommendations:/recommendations
      - /path/to/config/config.env:/config.env
```

Now run `docker compose up --build -d`

### Jellyfin Setup
To allow NextUp to be notified when a user favorites a recommendation and create a recommendation in Seerr you must setup a webhook to send notifications to NextUp.

1. In Jellyfin go to Dashboard -> Plugins
2. Install the Webhook plugin and restart your instance
3. After restart go to Dashboard -> Plugins -> Webhook -> Settings
4. Click "Add Generic Destination"
5. Provide a name that you will know what it means
6. Webhook URL
    1. Use `http://{HOST}:{PORT}/webhook/jellyfin`
7. Status
    1. Ensure `Enabled` is checked
8. Notification Type
    1. Ensure `User Data Saved` is checked
9. User Filter
    1. Check all users that should be able to automatically generate requests in Seerr by favoriting items
10. Item Type
    1. Ensure `Movies` and `Series` is checked
11. Ensure `Send All Properties (ignores template)` is checked
12. **DO NOT FORGET TO SAVE**

### WatchState Setup
To enable watchstate in your install you must provide the [WatchState configuration](#watchstate). Follow the [WatchState installation instructions](https://github.com/arabcoders/watchstate?tab=readme-ov-file#install) to setup your Jellyfin backend and users/sub-users. Don't forget to setup the Webhook for your backend.

## Configuration
NextUp uses a configuration file, `config.env` to customize NextUp Behavior. 

### Jellyfin

| Name             | Default | Description                                | Required    |
| ---------------- | ------- | ------------------------------------------ | ----------- |
| JELLYFIN_API_KEY |         | API key used to authenticate with Jellfyin | ✔️         |
| JELLYFIN_URL     |         | Base Jellyfin URL                          | ✔️         |

### Seerr

| Name             | Default | Description                                | Required    |
| ---------------- | ------- | ------------------------------------------ | ----------- |
| SEERR_API_KEY    |         | API key used to authenticate with Seerr    | ❌         |
| SEERR_URL        |         | Base Seer URL                              | ❌         |

### TMDB

| Name             | Default | Description                                | Required    |
| ---------------- | ------- | ------------------------------------------ | ----------- |
| TMDB_API_KEY     |         | API key used to authenticate with TMDB    | ✔️         |
| TMDB_URL         | https://api.themoviedb.org/3 | Base TMDB URL        | ✔️         |

### NextUp

| Name             | Default | Description                                | Required    |
| ---------------- | ------- | ------------------------------------------ | ----------- |
| NEXTUP_RECOMMENDATIONS_DIR | `/recommendations` | Base directory for NextUp to create recommendations in | ❌         |
| PLACEHOLDER_FILE_PATH | `/movie.mp4` | The path to the video file to use as a placeholder for the recommendations. If using Docker the file must be passed to the container. If not passed the default video file will be used. | ❌         |

### WatchState
| Name             | Default | Description                                | Required    |
| ---------------- | ------- | ------------------------------------------ | ----------- |
| WATCHSTATE_USERNAME |         | WatchState username to authenticate with | ❌         |
| WATCHSTATE_PASSWORD |         | WatchState password to authenticate with | ❌         |
| WATCHSTATE_URL      |         | Base WatchState URL                      | ❌         |
| WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP |  | See note below                 | ❌         |

The "default" or "main" user of WatchState is always named "main". Fetching user watch history for the "main" Jellyfin user will fail if the Jellyfin username is not also main.

For example, if the Jellyfin admin account username is "Fry" that is linked to the "main" WatchState user I would set `WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP` to "Fry"

### Recommendations
| Name             | Default | Description                                | Required    |
| ---------------- | ------- | ------------------------------------------ | ----------- |
| GENERATE_RECOS_FOR | (All users) | Comma separated list of users to generate recos for | ❌         |
| RECOMMENDATIONS_CRON_SCHEDULE |         | Cron expression used to schedule when recommendations are generated. If not supplied then no scheduler is started. | ❌         |

#### Series
| Name             | Default | Description                                | Required    |
| ---------------- | ------- | ------------------------------------------ | ----------- |
| DISABLE_SERIES_RECOMMENDATIONS | false | Whether to disable generating recommendations from/for series | ❌         |
| SERIES_LIBRARY_IDS |         | Comma separated list of library IDs to search series watch history for. Using this option effectively ensures NextUp Recommendations are ignored by NextUp on further runs. | ❌         |
| MAX_SERIES_DAYS_LOOKBACK      |         | The number of days lookback at watch history to generate recommendations from. If unset uses entire history. | ❌         |
| MAX_RECOMMENDATIONS_PER_SERIES | 10 | The max number of recommendations to add per watched series | ❌         |

#### Movie
| Name             | Default | Description                                | Required    |
| ---------------- | ------- | ------------------------------------------ | ----------- |
| DISABLE_MOVIE_RECOMMENDATIONS | false | Whether to disable generating recommendations from/for movies. | ❌         |
| MOVIE_LIBRARY_IDS |         | Comma separated list of library IDs to search movie watch history for. Using this option effectively ensures NextUp Recommendations are ignored by NextUp on further runs. | ❌         |
| MAX_MOVIE_DAYS_LOOKBACK      |         | The number of days lookback at watch history to generate recommendations from. If unset uses entire history. | ❌         |
| MAX_RECOMMENDATIONS_PER_MOVIE | 5 | The max number of recommendations to add per watched movie | ❌         |
| MIN_MOVIE_WATCH_PERCENT | 90 | The percentage that a movie must be watched to be considered for recommendations. This setting helps for movies that are still "in progress" at the credits | ❌ |
### [MIT License](LICENSE)

## Acknowledgments
Special thanks to the developers and maintainers of [Jellyfin](https://github.com/jellyfin/jellyfin), [Seerr](https://github.com/seerr-team/seerr), [WatchState](https://github.com/arabcoders/watchstate), and [TMDB](https://www.themoviedb.org/).

Thanks to the developers and maintainers of [Jellybridge Jellyfin Plugin](https://github.com/kinggeorges12/JellyBridge) for the inspiration for this project as well as the source of the [placeholder video file](movie.mp4)