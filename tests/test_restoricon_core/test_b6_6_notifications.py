import unittest
from unittest.mock import MagicMock
from restoricon_core.services.crm_service import CRMService
from restoricon_core.database import DatabaseManager
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.notification_service import NotificationService
from restoricon_core.auth import AuthContext, ROLE_ADMIN

class TestB66Notifications(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.audit = AuditService(self.db)
        self.notification_service = MagicMock(spec=NotificationService)
        self.crm_service = CRMService(self.db, self.audit, self.notification_service)
        
        # Setup initial data
        conn = self.db.get_connection()
        conn.execute("INSERT INTO users (id, username, password_hash, email, full_name, role, created_at, updated_at) VALUES (1, 'pm', 'hash', 'pm@example.com', 'John', 'project_manager', '2023', '2023')")
        conn.execute("INSERT INTO customers (id, first_name, last_name, email, created_at) VALUES (1, 'Jane', 'Doe', 'j@d.com', '2023')")
        conn.execute("INSERT INTO projects (id, customer_id, title, property_address, project_type, stage, created_at, updated_at) VALUES (1, 1, 'Proj', 'Addr', 'Type', 'intake', '2023', '2023')")
        conn.commit()

        self.actor = AuthContext(
            user_id=1,
            username='pm',
            role=ROLE_ADMIN,
            actor_type='human',
            customer_id=None
        )

    def test_update_project_manager_sends_notification(self):
        # Update project manager
        self.crm_service.update_project(1, {"project_manager_id": 1}, self.actor)
        
        # Assert notification was sent
        self.notification_service.send_email.assert_called_once_with(
            to_email='pm@example.com',
            subject='Project Assignment: Project 1',
            body='Hi John,\n\nYou have been assigned as the Project Manager for Project 1.'
        )

    def test_update_other_field_does_not_send_notification(self):
        # Update title
        self.crm_service.update_project(1, {"title": "New Proj"}, self.actor)
        
        # Assert no notification
        self.notification_service.send_email.assert_not_called()
        
    def test_update_project_manager_null_email_no_notification(self):
        conn = self.db.get_connection()
        conn.execute("INSERT INTO users (id, username, password_hash, email, full_name, role, created_at, updated_at) VALUES (2, 'pm2', 'hash', '', 'Jane', 'project_manager', '2023', '2023')")
        conn.commit()
        
        self.crm_service.update_project(1, {"project_manager_id": 2}, self.actor)
        self.notification_service.send_email.assert_not_called()

if __name__ == "__main__":
    unittest.main()
