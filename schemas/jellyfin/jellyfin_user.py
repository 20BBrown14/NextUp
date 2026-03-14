from dataclasses import dataclass
from typing import List, Optional, TypedDict

@dataclass
class JellyfinUserPolicy(TypedDict):
    IsAdministrator: bool
    IsHidden: bool
    EnableCollectionManagement: bool
    EnableSubtitleManagement: bool
    EnableLyricManagement: bool
    IsDisabled: bool
    BlockedTags: List[str]
    AllowedTags: List[str]
    EnableUserPreferenceAccess: bool
    AccessSchedules: List[str]
    BlockUnratedItems: List[str]
    EnableRemoteControlOfOtherUsers: bool
    EnableSharedDeviceControl: bool
    EnableRemoteAccess: bool
    EnableLiveTvManagement: bool
    EnableLiveTvAccess: bool
    EnableMediaPlayback: bool
    EnableAudioPlaybackTranscoding: bool
    EnableVideoPlaybackTranscoding: bool
    EnablePlaybackRemuxing: bool
    ForceRemoteSourceTranscoding: bool
    EnableContentDeletion: bool
    EnableContentDeletionFromFolders: List[str]
    EnableContentDownloading: bool
    EnableSyncTranscoding: bool
    EnableMediaConversion: bool
    EnabledDevices: List[str]
    EnableAllDevices: bool
    EnabledChannels: List[str]
    EnableAllChannels: bool
    EnabledFolders: List[str]
    EnableAllFolders: bool
    InvalidLoginAttemptCount: int
    LoginAttemptsBeforeLockout: int
    MaxActiveSessions: int
    EnablePublicSharing: bool
    BlockedMediaFolders: List[str]
    BlockedChannels: List[str]
    RemoteClientBitrateLimit: int
    AuthenticationProviderId: str
    PasswordResetProviderId: str
    SyncPlayAccess: str

@dataclass
class JellyfinUserConfiguration(TypedDict):
    AudioLanguagePreference: str
    PlayDefaultAudioTrack: bool
    SubtitleLanguagePreference: str
    DisplayMissingEpisodes: bool
    GroupedFolders: List[str]
    SubtitleMode: str
    DisplayCollectionsView: bool
    EnableLocalPassword: bool
    OrderedViews: List[str]
    LatestItemsExcludes: List[str]
    MyMediaExcludes: List[str]
    HidePlayedInLatest: bool
    RememberAudioSelections: bool
    RememberSubtitleSelections: bool
    EnableNextEpisodeAutoPlay: bool
    CastReceiverId: str

@dataclass
class JellyfinUser(TypedDict):
    Name: str
    ServerId: str
    Id: str
    PrimaryImageTag: str
    HasPassword: bool
    HasConfiguredPassword: bool
    HasConfiguredEasyPassword: bool
    EnableAutoLogin: bool
    LastLoginDate: str
    LastActivityDate: str
    Configuration: JellyfinUserConfiguration
    Policy: JellyfinUserPolicy

@dataclass
class JellyfinUserItemUserData(TypedDict):
    PlaybackPositionTicks: int
    PlayCount: int
    IsFavorite: bool
    LastPlayedDate: str
    Played: bool
    Key: str
    ItemId: str

@dataclass
class JellyfinUserItemImageTag(TypedDict):
    Logo: str
    Primary: str
    Thumb: str


@dataclass
class JellyfinUserItem(TypedDict):
    Name: str
    ServerId: str
    Id: str
    HasSubtitles: bool
    Container: str
    PremiereDate: str
    CriticRating: int
    OfficialRating: str
    ChannelId: str | None
    CommunityRating: float
    RunTimeTicks: int
    ProductionYear: int
    IsFolder: bool
    type: str
    UserData: JellyfinUserItemUserData
    VideoType: str
    ImageTags: JellyfinUserItemImageTag
    BackDropImageTags: List[str]
    LocationType: str
    MediaType: str
    