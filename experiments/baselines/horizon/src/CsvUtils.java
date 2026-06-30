import java.io.BufferedWriter;
import java.io.IOException;
import java.util.ArrayList;

/**
 * Shared CSV parsing and writing utilities for Horizon.
 *
 * The standard Java String.split(",") does not respect RFC-4180 quoting,
 * so quoted fields that contain commas get split incorrectly.  This class
 * provides a proper parser and writer that handle:
 *   - Fields wrapped in double-quotes
 *   - Embedded commas inside quoted fields
 *   - Escaped quotes (doubled: "")
 *   - Newlines inside quoted fields (treated as part of the value)
 */
public class CsvUtils {

    /**
     * Parse a single CSV line into an array of field values.
     *
     * Handles:
     *   - Unquoted fields (delimited by comma)
     *   - Quoted fields ("...") that may contain commas and escaped quotes ("")
     *
     * Trailing/leading whitespace inside quotes is preserved.
     *
     * @param line the raw CSV line (without the line terminator)
     * @return     array of parsed field values
     */
    public static String[] parseCsvLine(String line) {
        if (line == null || line.isEmpty()) {
            return new String[]{""};
        }

        ArrayList<String> fields = new ArrayList<>();
        int i = 0;
        int len = line.length();

        while (i < len) {
            if (line.charAt(i) == '"') {
                // --- quoted field ---
                StringBuilder sb = new StringBuilder();
                i++; // skip opening quote
                while (i < len) {
                    if (line.charAt(i) == '"') {
                        if (i + 1 < len && line.charAt(i + 1) == '"') {
                            // escaped quote
                            sb.append('"');
                            i += 2;
                        } else {
                            // closing quote
                            i++; // skip closing quote
                            break;
                        }
                    } else {
                        sb.append(line.charAt(i));
                        i++;
                    }
                }
                fields.add(sb.toString());
                // skip comma after closing quote (if any)
                if (i < len && line.charAt(i) == ',') {
                    i++;
                    // if comma is at the very end, there is one more empty field
                    if (i == len) {
                        fields.add("");
                    }
                }
            } else {
                // --- unquoted field ---
                int start = i;
                while (i < len && line.charAt(i) != ',') {
                    i++;
                }
                fields.add(line.substring(start, i));
                if (i < len) {
                    i++; // skip comma
                    // trailing comma → one more empty field
                    if (i == len) {
                        fields.add("");
                    }
                }
            }
        }

        return fields.toArray(new String[0]);
    }

    /**
     * Escape a single value for CSV output (RFC-4180).
     *
     * If the value contains a comma, double-quote, newline, or carriage
     * return, wrap it in double-quotes and double any internal quotes.
     *
     * @param value the raw value
     * @return      the CSV-safe representation
     */
    public static String csvEscape(String value) {
        if (value == null) return "";
        if (value.contains(",") || value.contains("\"")
                || value.contains("\n") || value.contains("\r")) {
            String escaped = value.replace("\"", "\"\"");
            return "\"" + escaped + "\"";
        }
        return value;
    }

    /**
     * Write a complete CSV line (fields separated by commas, terminated by
     * newline) with proper escaping.
     *
     * @param out  the writer to write to
     * @param vals the field values for one row
     * @throws IOException if writing fails
     */
    public static void writeCsvLine(BufferedWriter out, String[] vals) throws IOException {
        for (int i = 0; i < vals.length; i++) {
            out.write(csvEscape(vals[i]));
            if (i < vals.length - 1) {
                out.write(",");
            }
        }
        out.write("\n");
    }
}
