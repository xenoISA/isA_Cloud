// Package server utilities
// 文件名: cmd/postgres-service/server/utils.go
package server

import (
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/structpb"
	"google.golang.org/protobuf/types/known/timestamppb"

	pb "github.com/isa-cloud/isa_cloud/api/proto/postgres"
	common "github.com/isa-cloud/isa_cloud/api/proto/common"
)

// ========================================
// Metadata Helpers
// ========================================

func createSuccessMetadata() *common.ResponseMetadata {
	return &common.ResponseMetadata{
		Success:   true,
		Message:   "Operation completed successfully",
		Timestamp: timestamppb.New(time.Now()),
	}
}

func createErrorMetadata(err error) *common.ResponseMetadata {
	return &common.ResponseMetadata{
		Success:   false,
		Message:   err.Error(),
		Timestamp: timestamppb.New(time.Now()),
	}
}

func createErrorResponse[T any](err error) (T, error) {
	var zero T
	return zero, status.Error(codes.Internal, err.Error())
}

// ========================================
// Type Conversion Helpers
// ========================================

func convertProtoValuesToInterface(values []*structpb.Value) ([]interface{}, error) {
	result := make([]interface{}, len(values))
	for i, v := range values {
		result[i] = convertProtoValue(v)
	}
	return result, nil
}

func convertProtoValue(v *structpb.Value) interface{} {
	if v == nil {
		return nil
	}

	switch v.Kind.(type) {
	case *structpb.Value_NullValue:
		return nil
	case *structpb.Value_NumberValue:
		return v.GetNumberValue()
	case *structpb.Value_StringValue:
		return v.GetStringValue()
	case *structpb.Value_BoolValue:
		return v.GetBoolValue()
	case *structpb.Value_StructValue:
		return v.GetStructValue().AsMap()
	case *structpb.Value_ListValue:
		list := v.GetListValue()
		result := make([]interface{}, len(list.Values))
		for i, item := range list.Values {
			result[i] = convertProtoValue(item)
		}
		return result
	default:
		return nil
	}
}

// ========================================
// Row Collection Helpers
// ========================================

func collectRows(rows pgx.Rows) ([]*structpb.Struct, error) {
	var result []*structpb.Struct

	fieldDescriptions := rows.FieldDescriptions()

	for rows.Next() {
		values, err := rows.Values()
		if err != nil {
			return nil, fmt.Errorf("failed to get row values: %w", err)
		}

		rowMap := make(map[string]interface{})
		for i, fd := range fieldDescriptions {
			rowMap[string(fd.Name)] = convertValueForProtobuf(values[i])
		}

		rowStruct, err := structpb.NewStruct(rowMap)
		if err != nil {
			return nil, fmt.Errorf("failed to create struct: %w", err)
		}

		result = append(result, rowStruct)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows iteration error: %w", err)
	}

	return result, nil
}

// convertValueForProtobuf converts PostgreSQL values to protobuf-compatible types
func convertValueForProtobuf(value interface{}) interface{} {
	if value == nil {
		return nil
	}

	switch v := value.(type) {
	case time.Time:
		return v.Format(time.RFC3339)
	case *time.Time:
		if v != nil {
			return v.Format(time.RFC3339)
		}
		return nil
	case []byte:
		// Convert byte arrays to base64 strings
		return string(v)
	case []interface{}:
		// Convert arrays recursively
		result := make([]interface{}, len(v))
		for i, item := range v {
			result[i] = convertValueForProtobuf(item)
		}
		return result
	case map[string]interface{}:
		// Convert maps recursively
		result := make(map[string]interface{})
		for k, item := range v {
			result[k] = convertValueForProtobuf(item)
		}
		return result
	// Handle pgtype.Numeric (PostgreSQL NUMERIC/DECIMAL/REAL types)
	case pgtype.Numeric:
		if v.Valid {
			// Convert to float64 for protobuf
			f64, err := v.Float64Value()
			if err == nil {
				return f64.Float64
			}
		}
		return nil
	// Handle pgtype.Int4 (PostgreSQL INTEGER)
	case pgtype.Int4:
		if v.Valid {
			return int64(v.Int32)
		}
		return nil
	// Handle pgtype.Int8 (PostgreSQL BIGINT)
	case pgtype.Int8:
		if v.Valid {
			return v.Int64
		}
		return nil
	// Handle pgtype.Float4 (PostgreSQL REAL)
	case pgtype.Float4:
		if v.Valid {
			return float64(v.Float32)
		}
		return nil
	// Handle pgtype.Float8 (PostgreSQL DOUBLE PRECISION)
	case pgtype.Float8:
		if v.Valid {
			return v.Float64
		}
		return nil
	// Handle pgtype.Text (PostgreSQL TEXT/VARCHAR)
	case pgtype.Text:
		if v.Valid {
			return v.String
		}
		return nil
	// Handle pgtype.Bool (PostgreSQL BOOLEAN)
	case pgtype.Bool:
		if v.Valid {
			return v.Bool
		}
		return nil
	default:
		return value
	}
}

// ========================================
// SQL Building Helpers
// ========================================

func buildSelectSQL(req *pb.SelectFromRequest) (string, []interface{}) {
	schema := req.Schema
	if schema == "" {
		schema = "public"
	}

	// SELECT clause
	columns := "*"
	if len(req.Columns) > 0 {
		columns = strings.Join(req.Columns, ", ")
	}

	sql := fmt.Sprintf("SELECT %s FROM %s.%s", columns, schema, req.Table)
	var params []interface{}
	paramCounter := 1

	// WHERE clause
	if len(req.Where) > 0 {
		whereClauses := make([]string, 0, len(req.Where))
		for _, w := range req.Where {
			clause := fmt.Sprintf("%s %s $%d", w.Column, w.Operator, paramCounter)
			whereClauses = append(whereClauses, clause)
			params = append(params, convertProtoValue(w.Value))
			paramCounter++
		}
		sql += " WHERE " + strings.Join(whereClauses, " AND ")
	}

	// ORDER BY clause
	if len(req.OrderBy) > 0 {
		sql += " ORDER BY " + strings.Join(req.OrderBy, ", ")
	}

	// LIMIT clause
	if req.Limit > 0 {
		sql += fmt.Sprintf(" LIMIT %d", req.Limit)
	}

	// OFFSET clause
	if req.Offset > 0 {
		sql += fmt.Sprintf(" OFFSET %d", req.Offset)
	}

	return sql, params
}

func buildInsertSQL(req *pb.InsertIntoRequest) (string, []interface{}) {
	schema := req.Schema
	if schema == "" {
		schema = "public"
	}

	if len(req.Rows) == 0 {
		return "", nil
	}

	// 获取列名（从第一行）
	firstRow := req.Rows[0].AsMap()
	columns := make([]string, 0, len(firstRow))
	for col := range firstRow {
		columns = append(columns, col)
	}

	// 构建 INSERT SQL
	sql := fmt.Sprintf("INSERT INTO %s.%s (%s) VALUES ",
		schema, req.Table, strings.Join(columns, ", "))

	var params []interface{}
	paramCounter := 1
	valueClauses := make([]string, 0, len(req.Rows))

	for _, row := range req.Rows {
		rowMap := row.AsMap()
		placeholders := make([]string, 0, len(columns))

		for _, col := range columns {
			placeholders = append(placeholders, fmt.Sprintf("$%d", paramCounter))
			params = append(params, rowMap[col])
			paramCounter++
		}

		valueClauses = append(valueClauses, fmt.Sprintf("(%s)", strings.Join(placeholders, ", ")))
	}

	sql += strings.Join(valueClauses, ", ")

	if req.Returning {
		sql += " RETURNING *"
	}

	return sql, params
}

func buildUpdateSQL(req *pb.UpdateTableRequest) (string, []interface{}) {
	schema := req.Schema
	if schema == "" {
		schema = "public"
	}

	values := req.Values.AsMap()
	setClauses := make([]string, 0, len(values))
	var params []interface{}
	paramCounter := 1

	// SET clause
	for col, val := range values {
		setClauses = append(setClauses, fmt.Sprintf("%s = $%d", col, paramCounter))
		params = append(params, val)
		paramCounter++
	}

	sql := fmt.Sprintf("UPDATE %s.%s SET %s", schema, req.Table, strings.Join(setClauses, ", "))

	// WHERE clause
	if len(req.Where) > 0 {
		whereClauses := make([]string, 0, len(req.Where))
		for _, w := range req.Where {
			clause := fmt.Sprintf("%s %s $%d", w.Column, w.Operator, paramCounter)
			whereClauses = append(whereClauses, clause)
			params = append(params, convertProtoValue(w.Value))
			paramCounter++
		}
		sql += " WHERE " + strings.Join(whereClauses, " AND ")
	}

	if req.Returning {
		sql += " RETURNING *"
	}

	return sql, params
}

func buildDeleteSQL(req *pb.DeleteFromRequest) (string, []interface{}) {
	schema := req.Schema
	if schema == "" {
		schema = "public"
	}

	sql := fmt.Sprintf("DELETE FROM %s.%s", schema, req.Table)
	var params []interface{}
	paramCounter := 1

	// WHERE clause
	if len(req.Where) > 0 {
		whereClauses := make([]string, 0, len(req.Where))
		for _, w := range req.Where {
			clause := fmt.Sprintf("%s %s $%d", w.Column, w.Operator, paramCounter)
			whereClauses = append(whereClauses, clause)
			params = append(params, convertProtoValue(w.Value))
			paramCounter++
		}
		sql += " WHERE " + strings.Join(whereClauses, " AND ")
	}

	if req.Returning {
		sql += " RETURNING *"
	}

	return sql, params
}

// ========================================
// Transaction Helpers
// ========================================

func generateTransactionID() string {
	return uuid.New().String()
}
