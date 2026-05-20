import Foundation

enum JSONValue: Codable, Equatable, Identifiable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    var id: String { display }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            self = .object(try container.decode([String: JSONValue].self))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }

    var objectValue: [String: JSONValue]? {
        if case .object(let value) = self { return value }
        return nil
    }

    var arrayValue: [JSONValue]? {
        if case .array(let value) = self { return value }
        return nil
    }

    var stringValue: String? {
        if case .string(let value) = self { return value }
        return nil
    }

    var boolValue: Bool? {
        if case .bool(let value) = self { return value }
        return nil
    }

    var intValue: Int? {
        if case .number(let value) = self { return Int(value) }
        return nil
    }

    var doubleValue: Double? {
        if case .number(let value) = self { return value }
        return nil
    }

    var display: String {
        switch self {
        case .string(let value):
            value
        case .number(let value):
            value.rounded() == value ? String(Int(value)) : String(value)
        case .bool(let value):
            value ? "true" : "false"
        case .object(let value):
            "{\(value.count)}"
        case .array(let value):
            "[\(value.count)]"
        case .null:
            "null"
        }
    }

    func value(for path: String...) -> JSONValue? {
        var current: JSONValue? = self
        for key in path {
            current = current?.objectValue?[key]
        }
        return current
    }

    func prettyPrinted() -> String {
        guard let object = foundationObject,
              JSONSerialization.isValidJSONObject(object),
              let data = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys]),
              let text = String(data: data, encoding: .utf8)
        else {
            return display
        }
        return text
    }

    var foundationObject: Any? {
        switch self {
        case .string(let value):
            value
        case .number(let value):
            value
        case .bool(let value):
            value
        case .object(let value):
            value.compactMapValues(\.foundationObject)
        case .array(let value):
            value.compactMap(\.foundationObject)
        case .null:
            NSNull()
        }
    }
}

struct RawResponse: Decodable {
    let value: JSONValue

    init(from decoder: Decoder) throws {
        value = try JSONValue(from: decoder)
    }
}

extension Dictionary where Key == String, Value == JSONValue {
    func string(_ key: String) -> String? { self[key]?.stringValue }
    func bool(_ key: String) -> Bool? { self[key]?.boolValue }
    func int(_ key: String) -> Int? { self[key]?.intValue }
    func array(_ key: String) -> [JSONValue] { self[key]?.arrayValue ?? [] }
    func object(_ key: String) -> [String: JSONValue]? { self[key]?.objectValue }
    func value(_ path: String...) -> JSONValue? {
        var current: JSONValue?
        for (index, key) in path.enumerated() {
            if index == 0 {
                current = self[key]
            } else {
                current = current?.objectValue?[key]
            }
        }
        return current
    }
}
