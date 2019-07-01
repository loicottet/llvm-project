; RUN: llc < %s -verify-machineinstrs -stack-symbol-ordering=0 -mtriple="aarch64-unknown-linux-gnu" | FileCheck %s
; RUN: llc < %s -verify-machineinstrs -stack-symbol-ordering=0 -mtriple="aarch64-unknown-unknown-elf" | FileCheck %s

; This test is a sanity check to ensure statepoints are generating StackMap
; sections correctly.  This is not intended to be a rigorous test of the 
; StackMap format (see the stackmap tests for that).

target datalayout = "e-i64:64-f80:128-n8:16:32:64-S128"

declare zeroext i1 @return_i1()

define i1 @test(i32 addrspace(1)* %ptr_base, i32 %arg)
  gc "statepoint-example" {
; CHECK-LABEL: test:
; Do we see two spills for the local values and the store to the
; alloca?
; CHECK: sub sp, sp, #48
; CHECK: stp x30, x0, [sp, #32]
; CHECK: stp x8, xzr, [sp, #8]
; CHECK: bl return_i1
; CHECK: add sp, sp, #48
; CHECK: ret
entry:
  %metadata1 = alloca i32 addrspace(1)*, i32 2, align 8
  store i32 addrspace(1)* null, i32 addrspace(1)** %metadata1
  %ptr_derived = getelementptr i32, i32 addrspace(1)* %ptr_base, i32 %arg
  %safepoint_token = tail call token (i64, i32, i1 ()*, i32, i32, ...) @llvm.experimental.gc.statepoint.p0f_i1f(i64 0, i32 0, i1 ()* @return_i1, i32 0, i32 0, i32 0, i32 2, i32 addrspace(1)* %ptr_base, i32 addrspace(1)* null, i32 addrspace(1)* %ptr_base, i32 addrspace(1)* %ptr_derived, i32 addrspace(1)* null)
  %call1 = call zeroext i1 @llvm.experimental.gc.result.i1(token %safepoint_token)
  %a = call i32 addrspace(1)* @llvm.experimental.gc.relocate.p1i32(token %safepoint_token, i32 9, i32 9)
  %b = call i32 addrspace(1)* @llvm.experimental.gc.relocate.p1i32(token %safepoint_token, i32 9, i32 10)
  %c = call i32 addrspace(1)* @llvm.experimental.gc.relocate.p1i32(token %safepoint_token, i32 11, i32 11)
; 
  ret i1 %call1
}

; This is similar to the previous test except that we have derived pointer as
; argument to the function. Despite that this can not happen after the
; RewriteSafepointForGC pass, lowering should be able to handle it anyway.
define i1 @test_derived_arg(i32 addrspace(1)* %ptr_base,
                            i32 addrspace(1)* %ptr_derived)
  gc "statepoint-example" {
; CHECK-LABEL: test_derived_arg
; Do we see two spills for the local values and the store to the
; alloca?
; CHECK: sub sp, sp, #48
; CHECK: stp x30, x0, [sp, #32]
; CHECK: stp x1, xzr, [sp, #8]
; CHECK: bl return_i1
; CHECK: add sp, sp, #48
; CHECK: ret
entry:
  %metadata1 = alloca i32 addrspace(1)*, i32 2, align 8
  store i32 addrspace(1)* null, i32 addrspace(1)** %metadata1
  %safepoint_token = tail call token (i64, i32, i1 ()*, i32, i32, ...) @llvm.experimental.gc.statepoint.p0f_i1f(i64 0, i32 0, i1 ()* @return_i1, i32 0, i32 0, i32 0, i32 2, i32 addrspace(1)* %ptr_base, i32 addrspace(1)* null, i32 addrspace(1)* %ptr_base, i32 addrspace(1)* %ptr_derived, i32 addrspace(1)* null)
  %call1 = call zeroext i1 @llvm.experimental.gc.result.i1(token %safepoint_token)
  %a = call i32 addrspace(1)* @llvm.experimental.gc.relocate.p1i32(token %safepoint_token, i32 9, i32 9)
  %b = call i32 addrspace(1)* @llvm.experimental.gc.relocate.p1i32(token %safepoint_token, i32 9, i32 10)
  %c = call i32 addrspace(1)* @llvm.experimental.gc.relocate.p1i32(token %safepoint_token, i32 11, i32 11)
; 
  ret i1 %call1
}

; Simple test case to check that we emit the ID field correctly
define i1 @test_id() gc "statepoint-example" {
; CHECK-LABEL: test_id
entry:
  %safepoint_token = tail call token (i64, i32, i1 ()*, i32, i32, ...) @llvm.experimental.gc.statepoint.p0f_i1f(i64 237, i32 0, i1 ()* @return_i1, i32 0, i32 0, i32 0, i32 0)
  %call1 = call zeroext i1 @llvm.experimental.gc.result.i1(token %safepoint_token)
  ret i1 %call1
}

; This test checks that when SP is changed in the function
; (e.g. passing arguments on stack), the stack map entry
; takes this adjustment into account.
declare void @many_arg(i64, i64, i64, i64, i64, i64, i64, i64, i64, i64)

define i32 @test_spadj(i32 addrspace(1)* %p) gc "statepoint-example" {
  ; CHECK-LABEL: test_spadj
  ; CHECK: stp x30, x0, [sp, #16]
  ; CHECK: mov x0, xzr
  ; CHECK: mov x1, xzr
  ; CHECK: mov x2, xzr
  ; CHECK: mov x3, xzr
  ; CHECK: mov x4, xzr
  ; CHECK: mov x5, xzr
  ; CHECK: mov x6, xzr
  ; CHECK: mov x7, xzr
  ; CHECK: stp xzr, xzr, [sp]
  ; CHECK: bl many_arg
  ; CHECK: ldp  x30, x8, [sp, #16]
  %statepoint_token = call token (i64, i32, void (i64, i64, i64, i64, i64, i64, i64, i64, i64, i64)*, i32, i32, ...) @llvm.experimental.gc.statepoint.p0f_isVoidi64i64i64i64i64i64i64i64i64i64f(i64 0, i32 0, void (i64, i64, i64, i64, i64, i64, i64, i64, i64, i64)* @many_arg, i32 10, i32 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i64 0, i32 0, i32 0, i32 addrspace(1)* %p)
  %p.relocated = call i32 addrspace(1)* @llvm.experimental.gc.relocate.p1i32(token %statepoint_token, i32 17, i32 17) ; (%p, %p)
  %ld = load i32, i32 addrspace(1)* %p.relocated
  ret i32 %ld
}

; Test that function arguments at fixed stack offset
; can be directly encoded in the stack map, without
; spilling.
%struct = type { i64, i64, i64 }

declare void @use(%struct*)

define void @test_fixed_arg(%struct* byval %x) gc "statepoint-example" {
; CHECK-LABEL: test_fixed_arg
; CHECK: str x30, [sp, #-16]!
; CHECK: add x0, sp, #16
; Should not spill fixed stack address.
; CHECK-NOT: str x0, [sp]
; CHECK: bl use
; CHECK: ldr x30, [sp], #16
; CHECK: ret
entry:
  br label %bb

bb:                                               ; preds = %entry
  %statepoint_token = call token (i64, i32, void (%struct*)*, i32, i32, ...) @llvm.experimental.gc.statepoint.p0f_isVoidp0s_structsf(i64 0, i32 0, void (%struct*)* @use, i32 1, i32 0, %struct* %x, i32 0, i32 1, %struct* %x)
  ret void
}

declare token @llvm.experimental.gc.statepoint.p0f_i1f(i64, i32, i1 ()*, i32, i32, ...)
declare token @llvm.experimental.gc.statepoint.p0f_isVoidi64i64i64i64i64i64i64i64i64i64f(i64, i32, void (i64, i64, i64, i64, i64, i64, i64, i64, i64, i64)*, i32, i32, ...)
declare token @llvm.experimental.gc.statepoint.p0f_isVoidp0s_structsf(i64, i32, void (%struct*)*, i32, i32, ...)
declare i1 @llvm.experimental.gc.result.i1(token)
declare i32 addrspace(1)* @llvm.experimental.gc.relocate.p1i32(token, i32, i32) #3

; CHECK-LABEL: .section .llvm_stackmaps
; CHECK-NEXT:  __LLVM_StackMaps:
; Header
; CHECK-NEXT:   .byte 3
; CHECK-NEXT:   .byte 0
; CHECK-NEXT:   .hword 0
; Num Functions
; CHECK-NEXT:   .word 5
; Num LargeConstants
; CHECK-NEXT:   .word 0
; Num Callsites
; CHECK-NEXT:   .word 5

; Functions and stack size
; CHECK-NEXT:   .xword test
; CHECK-NEXT:   .xword 48
; CHECK-NEXT:   .xword 1
; CHECK-NEXT:   .xword test_derived_arg
; CHECK-NEXT:   .xword 48
; CHECK-NEXT:   .xword 1
; CHECK-NEXT:   .xword test_id
; CHECK-NEXT:   .xword 16
; CHECK-NEXT:   .xword 1
; CHECK-NEXT:   .xword test_spadj
; CHECK-NEXT:   .xword 32
; CHECK-NEXT:   .xword 1
; CHECK-NEXT:   .xword test_fixed_arg
; CHECK-NEXT:   .xword 16
; CHECK-NEXT:   .xword 1

;
; test
;

; Statepoint ID
; CHECK-NEXT: .xword	0

; Callsites
; Constant arguments
; CHECK-NEXT: .word	.Ltmp0-test
; CHECK: .hword	0
; CHECK: .hword	11
; SmallConstant (0)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0
; SmallConstant (0)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0
; SmallConstant (2)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	2
; Indirect Spill Slot [SP+40]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	40
; SmallConstant  (0)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0
; SmallConstant  (0)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0
; SmallConstant  (0)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0
; Indirect Spill Slot [SP+40]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	40
; Indirect Spill Slot [SP+8]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	8
; Indirect Spill Slot [SP+40]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	40
; Indirect Spill Slot [SP+40]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	40

; No Padding or LiveOuts
; CHECK: .hword	0
; CHECK: .hword	0
; CHECK: .p2align	3

;
; test_derived_arg

; Statepoint ID
; CHECK-NEXT: .xword	0

; Callsites
; Constant arguments
; CHECK-NEXT: .word	.Ltmp1-test_derived_arg
; CHECK: .hword	0
; CHECK: .hword	11
; SmallConstant (0)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0
; SmallConstant (2)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	2
; Indirect Spill Slot [SP+40]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	40
; SmallConstant  (0)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0
; SmallConstant  (0)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0
; SmallConstant  (0)
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0
; Indirect Spill Slot [SP+40]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	40
; Indirect Spill Slot [SP+8]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	8
; Indirect Spill Slot [SP+40]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	40
; Indirect Spill Slot [SP+40]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	40

; No Padding or LiveOuts
; CHECK: .hword	0
; CHECK: .hword	0
; CHECK: .p2align	3

; Records for the test_id function:

; The Statepoint ID:
; CHECK-NEXT: .xword	237

; Instruction Offset
; CHECK-NEXT: .word	.Ltmp2-test_id

; Reserved:
; CHECK: .hword	0

; NumLocations:
; CHECK: .hword	3

; StkMapRecord[0]:
; SmallConstant(0):
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0

; StkMapRecord[1]:
; SmallConstant(0):
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0

; StkMapRecord[2]:
; SmallConstant(0):
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0

; No padding or LiveOuts
; CHECK: .hword	0
; CHECK: .hword	0
; CHECK: .p2align	3

;
; test_spadj

; Statepoint ID
; CHECK-NEXT: .xword	0

; Instruction Offset
; CHECK-NEXT: .word	.Ltmp3-test_spadj

; Reserved:
; CHECK: .hword	0

; NumLocations:
; CHECK: .hword	5

; StkMapRecord[0]:
; SmallConstant(0):
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0

; StkMapRecord[1]:
; SmallConstant(0):
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0

; StkMapRecord[2]:
; SmallConstant(0):
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0

; StkMapRecord[3]:
; Indirect Spill Slot [SP+24]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	24

; StkMapRecord[4]:
; Indirect Spill Slot [SP+24]
; CHECK: .byte	3
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	24

; No padding or LiveOuts
; CHECK: .hword	0
; CHECK: .hword	0
; CHECK: .p2align	3

;
; test_fixed_arg

; Statepoint ID
; CHECK-NEXT: .xword	0

; Instruction Offset
; CHECK-NEXT: .word	.Ltmp4-test_fixed_arg

; Reserved:
; CHECK: .hword	0

; NumLocations:
; CHECK: .hword	4

; StkMapRecord[0]:
; SmallConstant(0):
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0

; StkMapRecord[1]:
; SmallConstant(0):
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	0

; StkMapRecord[2]:
; SmallConstant(1):
; CHECK: .byte	4
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	0
; CHECK-NEXT:   .hword  0
; CHECK: .word	1

; StkMapRecord[3]:
; Direct SP+16
; CHECK: .byte	2
; CHECK-NEXT:   .byte   0
; CHECK: .hword 8
; CHECK: .hword	31
; CHECK-NEXT:   .hword  0
; CHECK: .word	16

; No padding or LiveOuts
; CHECK: .hword	0
; CHECK: .hword	0
; CHECK: .p2align	3
