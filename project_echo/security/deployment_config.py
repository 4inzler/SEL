"""
Production Deployment Configuration
- Environment-based security settings
- Logging and monitoring
- Rate limiting
- API integration examples
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import hashlib


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('security_events.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('SecureAI')


class SecurityConfig:
    """
    Environment-based security configuration
    """

    # Security levels
    STRICT = {
        'max_risk_score': 0.5,
        'enable_pre_filter': True,
        'enable_post_validation': True,
        'enable_image_scanning': True,
        'sanitize_usernames': True,
        'sanitize_metadata': True,
        'log_all_attempts': True,
        'rate_limit_enabled': True
    }

    MODERATE = {
        'max_risk_score': 0.7,
        'enable_pre_filter': True,
        'enable_post_validation': True,
        'enable_image_scanning': True,
        'sanitize_usernames': True,
        'sanitize_metadata': True,
        'log_all_attempts': True,
        'rate_limit_enabled': True
    }

    RELAXED = {
        'max_risk_score': 0.85,
        'enable_pre_filter': False,  # Skip pre-filter for speed
        'enable_post_validation': True,
        'enable_image_scanning': False,  # Skip image scanning
        'sanitize_usernames': True,
        'sanitize_metadata': False,
        'log_all_attempts': False,
        'rate_limit_enabled': False
    }

    @staticmethod
    def from_environment() -> Dict[str, Any]:
        """Load configuration from environment variables"""
        env = os.getenv('SECURITY_LEVEL', 'MODERATE').upper()

        if env == 'STRICT':
            return SecurityConfig.STRICT
        elif env == 'RELAXED':
            return SecurityConfig.RELAXED
        else:
            return SecurityConfig.MODERATE


class RateLimiter:
    """
    Rate limiting to prevent abuse and DoS attacks
    """

    def __init__(
        self,
        max_requests_per_minute: int = 60,
        max_requests_per_hour: int = 1000,
        block_duration_minutes: int = 15
    ):
        self.max_per_minute = max_requests_per_minute
        self.max_per_hour = max_requests_per_hour
        self.block_duration = timedelta(minutes=block_duration_minutes)

        self.request_log = defaultdict(list)
        self.blocked_users = {}

    def _get_user_key(self, username: str, ip_address: Optional[str] = None) -> str:
        """Generate unique key for user"""
        identifier = f"{username}:{ip_address or 'unknown'}"
        return hashlib.sha256(identifier.encode()).hexdigest()

    def _cleanup_old_requests(self, user_key: str):
        """Remove requests older than 1 hour"""
        now = datetime.now()
        cutoff = now - timedelta(hours=1)

        self.request_log[user_key] = [
            req_time for req_time in self.request_log[user_key]
            if req_time > cutoff
        ]

    def is_blocked(self, username: str, ip_address: Optional[str] = None) -> bool:
        """Check if user is currently blocked"""
        user_key = self._get_user_key(username, ip_address)

        if user_key in self.blocked_users:
            unblock_time = self.blocked_users[user_key]
            if datetime.now() < unblock_time:
                return True
            else:
                # Unblock user
                del self.blocked_users[user_key]

        return False

    def check_rate_limit(
        self,
        username: str,
        ip_address: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Check if request should be allowed

        Returns:
            (allowed, reason)
        """
        user_key = self._get_user_key(username, ip_address)

        # Check if blocked
        if self.is_blocked(username, ip_address):
            return False, "User temporarily blocked due to rate limiting"

        # Cleanup old requests
        self._cleanup_old_requests(user_key)

        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)

        # Count recent requests
        requests_last_minute = sum(
            1 for req_time in self.request_log[user_key]
            if req_time > minute_ago
        )

        requests_last_hour = len(self.request_log[user_key])

        # Check limits
        if requests_last_minute >= self.max_per_minute:
            self.blocked_users[user_key] = now + self.block_duration
            logger.warning(
                f"Rate limit exceeded (per minute) for user {username[:20]}, "
                f"IP: {ip_address}, blocked for {self.block_duration.seconds // 60} minutes"
            )
            return False, f"Too many requests. Try again in {self.block_duration.seconds // 60} minutes."

        if requests_last_hour >= self.max_per_hour:
            self.blocked_users[user_key] = now + self.block_duration
            logger.warning(
                f"Rate limit exceeded (per hour) for user {username[:20]}, "
                f"IP: {ip_address}, blocked for {self.block_duration.seconds // 60} minutes"
            )
            return False, f"Hourly limit exceeded. Try again in {self.block_duration.seconds // 60} minutes."

        # Record this request
        self.request_log[user_key].append(now)

        return True, None


class SecurityMonitor:
    """
    Monitor and log security events
    """

    def __init__(self):
        self.event_counts = defaultdict(int)
        self.threat_log = []

    def log_event(
        self,
        event_type: str,
        username: str,
        details: Dict[str, Any],
        severity: str = 'INFO'
    ):
        """Log security event"""

        log_data = {
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'username': username[:50],  # Limit length
            'severity': severity,
            'details': details
        }

        # Log based on severity
        if severity == 'CRITICAL':
            logger.critical(f"Security Event: {event_type} - {username[:20]} - {details}")
        elif severity == 'WARNING':
            logger.warning(f"Security Event: {event_type} - {username[:20]} - {details}")
        else:
            logger.info(f"Security Event: {event_type} - {username[:20]}")

        # Track counts
        self.event_counts[event_type] += 1

        # Store threats
        if severity in ['WARNING', 'CRITICAL']:
            self.threat_log.append(log_data)

    def get_statistics(self) -> Dict[str, Any]:
        """Get security statistics"""
        return {
            'total_events': sum(self.event_counts.values()),
            'event_breakdown': dict(self.event_counts),
            'total_threats': len(self.threat_log),
            'recent_threats': self.threat_log[-10:]  # Last 10 threats
        }


class ProductionSecureAISystem:
    """
    Production-ready secure AI system with monitoring and rate limiting
    """

    def __init__(
        self,
        api_client,
        system_prompt: str,
        config: Optional[Dict[str, Any]] = None,
        enable_monitoring: bool = True,
        enable_rate_limiting: bool = True
    ):
        from complete_secure_system import CompleteSecureAISystem

        self.config = config or SecurityConfig.from_environment()

        # Initialize core system
        self.secure_system = CompleteSecureAISystem(
            api_client=api_client,
            system_prompt=system_prompt,
            max_risk_score=self.config['max_risk_score']
        )

        # Initialize monitoring and rate limiting
        self.monitor = SecurityMonitor() if enable_monitoring else None
        self.rate_limiter = RateLimiter() if enable_rate_limiting and self.config['rate_limit_enabled'] else None

        logger.info(f"Initialized ProductionSecureAISystem with config: {self.config}")

    def process_request(
        self,
        username: str,
        message: str,
        metadata: Optional[Dict] = None,
        images: Optional[list] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process request with monitoring and rate limiting
        """

        # Rate limiting check
        if self.rate_limiter:
            allowed, reason = self.rate_limiter.check_rate_limit(username, ip_address)

            if not allowed:
                if self.monitor:
                    self.monitor.log_event(
                        event_type='rate_limit_exceeded',
                        username=username,
                        details={'ip': ip_address, 'reason': reason},
                        severity='WARNING'
                    )

                return {
                    'status': 'blocked',
                    'reason': reason,
                    'error_code': 'RATE_LIMIT_EXCEEDED'
                }

        # Process through secure system
        try:
            response = self.secure_system.process_secure_request(
                username=username,
                message=message,
                metadata=metadata,
                images=images
            )

            # Log event
            if self.monitor:
                severity = 'INFO'
                event_type = 'request_processed'

                if response.status == 'blocked':
                    severity = 'WARNING'
                    event_type = 'threat_blocked'

                self.monitor.log_event(
                    event_type=event_type,
                    username=username,
                    details={
                        'status': response.status,
                        'blocked_at': response.security_report.get('blocked_at'),
                        'threats': response.security_report.get('threats_detected', [])
                    },
                    severity=severity
                )

            return {
                'status': response.status,
                'content': response.content,
                'reason': response.reason,
                'security_report': response.security_report
            }

        except Exception as e:
            logger.error(f"Error processing request: {str(e)}")

            if self.monitor:
                self.monitor.log_event(
                    event_type='processing_error',
                    username=username,
                    details={'error': str(e)},
                    severity='CRITICAL'
                )

            return {
                'status': 'error',
                'reason': 'Internal processing error',
                'error_code': 'INTERNAL_ERROR'
            }

    def get_statistics(self) -> Dict[str, Any]:
        """Get system statistics"""
        if self.monitor:
            return self.monitor.get_statistics()
        return {}


# API Integration Example (Flask)
def create_flask_app():
    """Example Flask application with secure AI"""
    from flask import Flask, request, jsonify
    from anthropic import Anthropic

    app = Flask(__name__)

    # Initialize secure system
    client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    system_prompt = "You are a helpful AI assistant."

    secure_ai = ProductionSecureAISystem(
        api_client=client,
        system_prompt=system_prompt,
        enable_monitoring=True,
        enable_rate_limiting=True
    )

    @app.route('/api/chat', methods=['POST'])
    def chat():
        """Secure chat endpoint"""
        data = request.get_json()

        # Extract request data
        username = data.get('username', 'Anonymous')
        message = data.get('message', '')
        metadata = data.get('metadata', {})
        ip_address = request.remote_addr

        # Process securely
        result = secure_ai.process_request(
            username=username,
            message=message,
            metadata=metadata,
            ip_address=ip_address
        )

        # Return response
        if result['status'] == 'success':
            return jsonify({
                'response': result['content'],
                'status': 'success'
            }), 200
        elif result['status'] == 'blocked':
            return jsonify({
                'error': result['reason'],
                'status': 'blocked'
            }), 403
        else:
            return jsonify({
                'error': 'Internal error',
                'status': 'error'
            }), 500

    @app.route('/api/stats', methods=['GET'])
    def stats():
        """Get security statistics"""
        return jsonify(secure_ai.get_statistics()), 200

    return app


# FastAPI Integration Example
def create_fastapi_app():
    """Example FastAPI application with secure AI"""
    from fastapi import FastAPI, Request, HTTPException
    from pydantic import BaseModel
    from anthropic import Anthropic

    app = FastAPI()

    # Initialize secure system
    client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    system_prompt = "You are a helpful AI assistant."

    secure_ai = ProductionSecureAISystem(
        api_client=client,
        system_prompt=system_prompt
    )

    class ChatRequest(BaseModel):
        username: str
        message: str
        metadata: dict = {}

    @app.post('/api/chat')
    async def chat(chat_req: ChatRequest, request: Request):
        """Secure chat endpoint"""

        result = secure_ai.process_request(
            username=chat_req.username,
            message=chat_req.message,
            metadata=chat_req.metadata,
            ip_address=request.client.host
        )

        if result['status'] == 'success':
            return {'response': result['content'], 'status': 'success'}
        elif result['status'] == 'blocked':
            raise HTTPException(status_code=403, detail=result['reason'])
        else:
            raise HTTPException(status_code=500, detail='Internal error')

    @app.get('/api/stats')
    async def stats():
        """Get security statistics"""
        return secure_ai.get_statistics()

    return app


if __name__ == "__main__":
    print("Production Deployment Configuration")
    print("="*80)
    print("\nAvailable configurations:")
    print("- STRICT: Maximum security, slower performance")
    print("- MODERATE: Balanced security and performance (default)")
    print("- RELAXED: Faster performance, reduced security checks")
    print("\nSet via environment variable: SECURITY_LEVEL=STRICT|MODERATE|RELAXED")
    print("\nExample usage:")
    print("  from deployment_config import create_flask_app")
    print("  app = create_flask_app()")
    print("  app.run()")
