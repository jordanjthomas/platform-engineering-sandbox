import logging

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

logger = logging.getLogger("namespace_provisioner.k8s")

MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
MANAGED_BY_VALUE = "namespace-provisioner"


class KubernetesClient:
    def __init__(self, in_cluster: bool = True):
        if in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config()
        self.core_v1 = client.CoreV1Api()
        self.networking_v1 = client.NetworkingV1Api()

    def get_namespace(self, name: str):
        try:
            return self.core_v1.read_namespace(name)
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    def list_managed_namespaces(
        self,
        team: str | None = None,
        environment: str | None = None,
    ) -> list:
        label_selector = f"{MANAGED_BY_LABEL}={MANAGED_BY_VALUE}"
        if team:
            label_selector += f",team={team}"
        if environment:
            label_selector += f",environment={environment}"
        result = self.core_v1.list_namespace(label_selector=label_selector)
        return result.items

    def create_namespace(self, name: str, labels: dict) -> None:
        body = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=name, labels=labels)
        )
        self.core_v1.create_namespace(body=body)
        logger.info("Created namespace %s", name)

    def create_or_update_resource_quota(
        self, namespace: str, hard: dict
    ) -> None:
        body = client.V1ResourceQuota(
            metadata=client.V1ObjectMeta(name="default"),
            spec=client.V1ResourceQuotaSpec(hard=hard),
        )
        try:
            self.core_v1.read_namespaced_resource_quota("default", namespace)
            self.core_v1.replace_namespaced_resource_quota(
                "default", namespace, body=body
            )
            logger.info("Updated ResourceQuota in %s", namespace)
        except ApiException as e:
            if e.status == 404:
                self.core_v1.create_namespaced_resource_quota(
                    namespace, body=body
                )
                logger.info("Created ResourceQuota in %s", namespace)
            else:
                raise

    def create_or_update_limit_range(
        self, namespace: str, default: dict, default_request: dict
    ) -> None:
        body = client.V1LimitRange(
            metadata=client.V1ObjectMeta(name="default"),
            spec=client.V1LimitRangeSpec(
                limits=[
                    client.V1LimitRangeItem(
                        type="Container",
                        default=default,
                        default_request=default_request,
                    )
                ]
            ),
        )
        try:
            self.core_v1.read_namespaced_limit_range("default", namespace)
            self.core_v1.replace_namespaced_limit_range(
                "default", namespace, body=body
            )
            logger.info("Updated LimitRange in %s", namespace)
        except ApiException as e:
            if e.status == 404:
                self.core_v1.create_namespaced_limit_range(
                    namespace, body=body
                )
                logger.info("Created LimitRange in %s", namespace)
            else:
                raise

    def create_or_update_network_policy(
        self, namespace: str, name: str, spec: client.V1NetworkPolicySpec
    ) -> None:
        body = client.V1NetworkPolicy(
            metadata=client.V1ObjectMeta(name=name),
            spec=spec,
        )
        try:
            self.networking_v1.read_namespaced_network_policy(name, namespace)
            self.networking_v1.replace_namespaced_network_policy(
                name, namespace, body=body
            )
            logger.info("Updated NetworkPolicy %s in %s", name, namespace)
        except ApiException as e:
            if e.status == 404:
                self.networking_v1.create_namespaced_network_policy(
                    namespace, body=body
                )
                logger.info("Created NetworkPolicy %s in %s", name, namespace)
            else:
                raise

    def get_resource_quota(self, namespace: str):
        try:
            return self.core_v1.read_namespaced_resource_quota(
                "default", namespace
            )
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    def list_pods(self, namespace: str) -> int:
        result = self.core_v1.list_namespaced_pod(namespace)
        return len(result.items)

    def delete_namespace(self, name: str) -> None:
        self.core_v1.delete_namespace(name)
        logger.info("Deleted namespace %s", name)
