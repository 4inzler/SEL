"""
Confidence scoring for SEL responses
Helps SEL express uncertainty naturally and improve over time
"""
from typing import Dict, Optional, List
import re
from datetime import datetime, timezone


class ConfidenceScorer:
    """Analyze and track confidence in SEL's responses"""

    def __init__(self):
        self._confidence_history: List[Dict] = []

    def assess_response_confidence(
        self,
        user_query: str,
        sel_response: str,
        memories_count: int,
        context: Optional[str] = None
    ) -> Dict:
        """
        Assess confidence in SEL's response

        Args:
            user_query: User's question/message
            sel_response: SEL's generated response
            memories_count: Number of memories retrieved
            context: Additional context (presence, weather, etc.)

        Returns:
            Confidence assessment dict with score and factors
        """
        score = 70  # Base confidence
        factors = []

        # Factor 1: Uncertainty indicators in response
        uncertainty_phrases = [
            "not sure", "don't know", "maybe", "might", "could be",
            "i think", "probably", "possibly", "dunno", "idk",
            "unsure", "uncertain", "guess", "not certain"
        ]
        response_lower = sel_response.lower()
        uncertainty_count = sum(1 for phrase in uncertainty_phrases if phrase in response_lower)

        if uncertainty_count >= 3:
            score -= 20
            factors.append("High uncertainty language")
        elif uncertainty_count >= 1:
            score -= 10
            factors.append("Some uncertainty")
        else:
            score += 5
            factors.append("Confident language")

        # Factor 2: Memory support
        if memories_count == 0:
            score -= 15
            factors.append("No memory support")
        elif memories_count >= 3:
            score += 10
            factors.append(f"{memories_count} memories retrieved")
        else:
            score += 5
            factors.append(f"{memories_count} memories")

        # Factor 3: Question complexity
        is_complex = any([
            len(user_query.split()) > 15,
            "why" in user_query.lower(),
            "how does" in user_query.lower(),
            "explain" in user_query.lower(),
            "?" in user_query and "," in user_query
        ])
        if is_complex:
            score -= 5
            factors.append("Complex question")

        # Factor 4: Response length (very short might indicate uncertainty)
        if len(sel_response) < 20:
            score -= 10
            factors.append("Very brief response")
        elif len(sel_response) > 200:
            score += 5
            factors.append("Detailed response")

        # Factor 5: Hedging phrases
        hedging = ["kind of", "sort of", "kinda", "sorta", "like maybe"]
        hedging_count = sum(1 for phrase in hedging if phrase in response_lower)
        if hedging_count >= 2:
            score -= 10
            factors.append("Excessive hedging")

        # Factor 6: Direct questions in response (asking for clarification)
        questions_in_response = sel_response.count("?")
        if questions_in_response >= 2:
            score -= 10
            factors.append("Seeking clarification")

        # Clamp score to 0-100
        score = max(0, min(100, score))

        # Determine confidence level
        if score >= 85:
            level = "very_high"
            label = "Very Confident"
        elif score >= 70:
            level = "high"
            label = "Confident"
        elif score >= 50:
            level = "medium"
            label = "Moderate"
        elif score >= 30:
            level = "low"
            label = "Uncertain"
        else:
            level = "very_low"
            label = "Very Uncertain"

        assessment = {
            "score": score,
            "level": level,
            "label": label,
            "factors": factors,
            "timestamp": datetime.now(timezone.utc),
            "user_query": user_query[:100],  # Truncate for storage
            "response_length": len(sel_response)
        }

        # Track history
        self._confidence_history.append(assessment)
        if len(self._confidence_history) > 100:
            self._confidence_history = self._confidence_history[-100:]

        return assessment

    def get_confidence_guidance(self, confidence_score: int) -> str:
        """
        Get guidance for prompt based on expected confidence

        Args:
            confidence_score: Expected confidence (0-100)

        Returns:
            Guidance text for prompt
        """
        if confidence_score >= 80:
            return (
                "You're confident in this response. Be direct and clear."
            )
        elif confidence_score >= 60:
            return (
                "You have moderate confidence. It's ok to say 'i think' or 'probably' "
                "when you're not 100% sure."
            )
        elif confidence_score >= 40:
            return (
                "You're uncertain about this. It's completely fine to say "
                "'i'm not sure' or 'might be' - honesty builds trust."
            )
        else:
            return (
                "You don't know or are very uncertain. Be honest: 'idk', 'not sure', "
                "'dunno' - it's better to admit uncertainty than fake confidence."
            )

    def get_statistics(self) -> Dict:
        """
        Get confidence statistics

        Returns:
            Statistics dict
        """
        if not self._confidence_history:
            return {
                "total_responses": 0,
                "average_confidence": 0,
                "confidence_trend": "unknown"
            }

        scores = [h["score"] for h in self._confidence_history]
        avg = sum(scores) / len(scores)

        # Trend: compare recent vs older
        if len(scores) >= 10:
            recent_avg = sum(scores[-10:]) / 10
            older_avg = sum(scores[:-10]) / len(scores[:-10])
            if recent_avg > older_avg + 5:
                trend = "improving"
            elif recent_avg < older_avg - 5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "total_responses": len(self._confidence_history),
            "average_confidence": round(avg, 1),
            "confidence_trend": trend,
            "recent_scores": scores[-5:]
        }

    def should_warn_low_confidence(self, score: int) -> bool:
        """Check if low confidence warning should be shown"""
        return score < 40


def get_confidence_emoji(score: int) -> str:
    """Get emoji for confidence level"""
    if score >= 85:
        return "💯"  # Very confident
    elif score >= 70:
        return "✅"  # Confident
    elif score >= 50:
        return "🤔"  # Moderate
    elif score >= 30:
        return "❓"  # Uncertain
    else:
        return "🤷"  # Very uncertain
