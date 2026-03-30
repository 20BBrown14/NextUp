# NextUp
NextUp is a program that allows [Jellyfin](https://jellyfin.org/) admins to generate user personalized movie and series recommendations directly in Jellyfin regardless of client using Jellyfin libraries. User are also able to generate media requests in [Seer](https://seerr.dev/) right from the Jellyfin UI by favoriting the media in their recommendations.

NextUp is also compatible with [WatchState](https://github.com/arabcoders/watchstate) to allow for more long live watch history to improve recommendations and avoid getting recommendations for media the user has already watched but might have been removed from the server.

## Features
- Support for any number of users
- Optional WatchState integration
- Optional Seerr integration

## How It Works
NextUp looks at a user's movie and series watch history and uses that to query [TMDB](https://www.themoviedb.org/?language=en-US) for recommendations based on that watched piece of media. It then creates a minimal `metadata.json` file and saves it in a directory specific for that user in a place that Jellyfin can import along with a dummy video file. Jellyfin admins then create a library for that user's recommendations and allow then allow that user to see that library. 

If the Seerr integration is enabled in NextUp users can favorite media from their recommendations to automatically request it for download in Seerr. Note that due to the way Seerr's api is implemented [all requests are auto-approved](https://github.com/seerr-team/seerr/issues/2678#issuecomment-4038790777).

### Watch History Limitation
Jellyfin's API only returns watch history for media currently on the server therefore users with a small changing library would not get the benefit of a long standing watch history to pull recommendations from.

[WatchState](https://github.com/arabcoders/watchstate) is a self-hostable tool that was originally designed to 
> sync your backends users play state without relying on third party services

However it also stores watch history for all media a user has watched regardless of the status on the media on the server. Using WatchState's API NextUp can fetch a complete watch history. WatchState stores actual watch history AND user-marked watched media. As a result users can "Mark as Watched" media in their recommendations to avoid recommending it in the future as well as use it as a seed for further recommendations.

## Installation / Usage
The easiest way to use NextUp is to use the Docker image but you also build from source or run using Python directly.

### Docker Image
```yaml

```