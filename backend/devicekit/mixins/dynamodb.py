import os
import json
import boto3
import uuid
import logging
from boto3.dynamodb.conditions import Key, Attr
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class DynamodbMixin:
    DYNAMODB_CLIENT = None

    def create_dynamodb_connection(self):
        kwargs = {
            'aws_access_key_id': os.getenv("AWS_ACCESS_KEY_ID"),
            'aws_secret_access_key': os.getenv("AWS_SECRET_ACCESS_KEY"),
            'region_name': os.getenv("AWS_REGION", "us-east-1"),
        }
        endpoint = os.getenv("DYNAMODB_ENDPOINT")
        if endpoint:
            kwargs['endpoint_url'] = endpoint
        self.DYNAMODB_CLIENT = boto3.resource('dynamodb', **kwargs)
        return self.DYNAMODB_CLIENT

    def get_dynamodb_table(self, table_name, limit=0):
        dynamodb = self.create_dynamodb_connection()
        table = dynamodb.Table(table_name)
        response = table.scan()
        data = response['Items']
        while 'LastEvaluatedKey' in response:
            if limit != 0 and len(data) > limit:
                break
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            data.extend(response['Items'])
        return data

    def create_dynamodb_record(self, table_name, records):
        dynamodb = self.create_dynamodb_connection()
        table = dynamodb.Table(table_name)
        table.put_item(Item=records)

    def get_dynamodb_record(self, table_name, record_id, key="id"):
        dynamodb = self.create_dynamodb_connection()
        table = dynamodb.Table(table_name)
        try:
            response = table.get_item(Key={key: record_id})
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error retrieving record {key}={record_id} from {table_name}: {e}")
            return None

    def update_dynamodb_record(self, table_name, record_id, update_values, key="id"):
        dynamodb = self.create_dynamodb_connection()
        table = dynamodb.Table(table_name)
        existing = self.get_dynamodb_record(table_name, record_id, key)
        if not existing:
            return None
        existing.update(update_values)
        try:
            return table.put_item(Item=existing)
        except Exception as e:
            logger.error(f"Error updating record: {e}")
            return None

    def get_dynamodb_record_by_attr(self, table_name, record_id, attr_key="id"):
        dynamodb = self.create_dynamodb_connection()
        table = dynamodb.Table(table_name)
        response = table.scan(FilterExpression=Attr(attr_key).eq(record_id))
        try:
            return response['Items'][0]
        except (IndexError, KeyError):
            return None

    def check_if_record_exists(self, table_name, name):
        try:
            record = self.get_dynamodb_record_by_attr(table_name, name)
            return record is not None
        except Exception as e:
            logger.error(f"Error checking record in {table_name}: {e}")
            return False

    def ensure_table_exists(self, table_name, partition_key='id', sort_key=None,
                            partition_key_type='S', sort_key_type='S'):
        try:
            dynamodb = self.create_dynamodb_connection()
            existing = [t.name for t in dynamodb.tables.all()]
            if table_name in existing:
                return True

            key_schema = [{'AttributeName': partition_key, 'KeyType': 'HASH'}]
            attr_defs = [{'AttributeName': partition_key, 'AttributeType': partition_key_type}]
            if sort_key:
                key_schema.append({'AttributeName': sort_key, 'KeyType': 'RANGE'})
                attr_defs.append({'AttributeName': sort_key, 'AttributeType': sort_key_type})

            table = dynamodb.create_table(
                TableName=table_name,
                KeySchema=key_schema,
                AttributeDefinitions=attr_defs,
                ProvisionedThroughput={'ReadCapacityUnits': 10, 'WriteCapacityUnits': 10}
            )
            table.wait_until_exists()
            logger.info(f"Created table {table_name}")
            return True
        except Exception as e:
            logger.error(f"Error creating/checking table {table_name}: {e}")
            return False

    def count_records(self, table_name):
        try:
            dynamodb = self.create_dynamodb_connection()
            table = dynamodb.Table(table_name)
            response = table.scan(Select='COUNT')
            count = response['Count']
            while 'LastEvaluatedKey' in response:
                response = table.scan(Select='COUNT', ExclusiveStartKey=response['LastEvaluatedKey'])
                count += response['Count']
            return count
        except Exception as e:
            logger.error(f"Error counting records in {table_name}: {e}")
            return 0
