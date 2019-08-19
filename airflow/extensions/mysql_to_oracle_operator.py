from airflow.models import BaseOperator
from airflow.hooks.oracle_hook import OracleHook
from airflow.hooks.mysql_hook import MySqlHook


class MysqlToOracleOperator(BaseOperator):
    template_fields = ('source_sql', 'source_sql_params')

    def __init__(self, mysql_source_conn_id,
                 source_sql,
                 oracle_destination_conn_id,
                 destination_table,
                 source_sql_params=None,
                 rows_chunk=5000,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        if source_sql_params is None:
            source_sql_params = {}

        self.mysql_source_conn_id = mysql_source_conn_id
        self.source_sql = source_sql
        self.source_sql_params = source_sql_params
        self.oracle_destination_conn_id = oracle_destination_conn_id
        self.destination_table = destination_table
        self.rows_chunk = rows_chunk

    def _execute(self, src_hook, dest_hook, context):
        # 先truncate目标表
        dest_con = dest_hook.get_conn()
        dest_cursor = dest_con.cursor()
        dest_truncate_sql = 'truncate table {d_t_n}'.format(d_t_n=self.destination_table)
        dest_cursor.execute(dest_truncate_sql)
        dest_hook.log.info('truncate destination table  %s ', self.destination_table)
        dest_cursor.close()
        dest_con.close()

        with src_hook.get_conn() as src_conn:
            self.log.info("Querying data from source: %s", self.mysql_source_conn_id)
            src_conn.execute(self.source_sql, self.source_sql_params)
            target_fields = list(map(lambda field: field[0], src_conn.description))
            rows_total = 0
            rows = src_conn.fetchmany(self.rows_chunk)

            while len(rows) > 0:

                rows_total = rows_total + len(rows)
                dest_hook.bulk_insert_rows(self.destination_table,
                                           rows,
                                           target_fields=target_fields,
                                           commit_every=self.rows_chunk)
                rows = src_conn.fetchmany(self.rows_chunk)
                self.log.info("Total inserted: %s rows", rows_total)

            self.log.info("Finished data transfer.")
            src_conn.close()

    def execute(self, context):
        src_hook = MySqlHook(mysql_conn_id=self.mysql_source_conn_id)
        dest_hook = OracleHook(oracle_conn_id=self.oracle_destination_conn_id)
        self._execute(src_hook, dest_hook, context)
