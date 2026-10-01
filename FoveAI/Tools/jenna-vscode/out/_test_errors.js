"use strict";
/**
 * _test_errors.ts — DELIBERATE ERRORS FOR TESTING
 * Delete this file after confirming the Send Problems button works.
 */
Object.defineProperty(exports, "__esModule", { value: true });
// ERROR 1: Type mismatch
const x = "this is not a number";
// ERROR 2: Undefined variable
console.log(undefinedVariable);
// ERROR 3: Missing required argument
function greet(name, age) {
    return `Hello ${name}, you are ${age}`;
}
greet("Jenna"); // missing 'age' argument
// ERROR 4: Property does not exist
const obj = { a: 1 };
console.log(obj.nonExistentProperty);
// WARNING: unused variable (ts lint)
const unusedVar = 42;
//# sourceMappingURL=_test_errors.js.map