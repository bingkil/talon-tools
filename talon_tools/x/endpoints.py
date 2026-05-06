"""GraphQL endpoint definitions — query IDs and variable builders."""

from __future__ import annotations

# These query IDs are extracted from X's web client JS bundle.
# They change occasionally — re-capture from devtools if requests fail.

HOME_TIMELINE_QUERY_ID = "jYMvLJJjGjO3aKWY3bP5HA"
SEARCH_TIMELINE_QUERY_ID = "BqWLX1Tjvgh6eSZWEMH_kw"
TWEET_DETAIL_QUERY_ID = "B3ZxDiQ__9OXTkCCuAp79w"

BASE_URL = "https://x.com/i/api/graphql"

# Common feature flags required by X's GraphQL endpoints.
# Superset of all flags needed by HomeTimeline, SearchTimeline, TweetDetail.
_FEATURES = {
    "rweb_video_screen_enabled": True,
    "rweb_cashtags_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": True,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": False,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": False,
    "responsive_web_grok_annotations_enabled": False,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": False,
    "post_ctas_fetch_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": False,
    "responsive_web_grok_imagine_annotation_enabled": False,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}

# Field toggles required by some endpoints (e.g. SearchTimeline).
_FIELD_TOGGLES = {
    "withArticleRichContentState": True,
    "withArticlePlainText": False,
    "withGrokAnalyze": False,
    "withDisallowedReplyControls": False,
}


def home_timeline_vars(count: int = 20, cursor: str | None = None) -> dict:
    """Build variables for HomeTimeline query."""
    v: dict = {
        "count": count,
        "includePromotedContent": False,
        "latestControlAvailable": True,
    }
    if cursor:
        v["cursor"] = cursor
    return v


def search_timeline_vars(query: str, count: int = 20, cursor: str | None = None) -> dict:
    """Build variables for SearchTimeline query."""
    v: dict = {
        "rawQuery": query,
        "count": count,
        "querySource": "typed_query",
        "product": "Latest",
    }
    if cursor:
        v["cursor"] = cursor
    return v


def tweet_detail_vars(tweet_id: str) -> dict:
    """Build variables for TweetDetail query."""
    return {
        "focalTweetId": tweet_id,
        "with_rux_injections": False,
        "includePromotedContent": False,
        "withCommunity": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withBirdwatchNotes": True,
        "withVoice": True,
        "withV2Timeline": True,
    }


def features() -> dict:
    """Return the feature flags dict."""
    return dict(_FEATURES)


def field_toggles() -> dict:
    """Return the field toggles dict."""
    return dict(_FIELD_TOGGLES)
