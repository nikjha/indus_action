from locust import HttpUser, between, task


class ApiGatewayUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task
    def get_my_tasks(self):
        self.client.get("/my-eligible-tasks?user_id=4")

    @task
    def get_task_users(self):
        self.client.get("/tasks/1/eligible-users")
