CLASS ltc_meter_billing DEFINITION
  FINAL
  FOR TESTING
  DURATION SHORT
  RISK LEVEL HARMLESS.

  PRIVATE SECTION.
    DATA cut TYPE REF TO zcl_meter_billing.

    METHODS setup.
    METHODS calculates_valid_bill FOR TESTING.
    METHODS rejects_decreasing_reading FOR TESTING.
ENDCLASS.


CLASS ltc_meter_billing IMPLEMENTATION.
  METHOD setup.
    cut = NEW zcl_meter_billing( ).
  ENDMETHOD.

  METHOD calculates_valid_bill.
    DATA(result) = cut->calculate_bill(
      iv_previous_reading = '12450'
      iv_current_reading  = '12820' ).

    cl_abap_unit_assert=>assert_equals(
      act = result-consumption_kwh
      exp = '370' ).

    cl_abap_unit_assert=>assert_equals(
      act = result-total_amount
      exp = '168.385' ).
  ENDMETHOD.

  METHOD rejects_decreasing_reading.
    TRY.
        cut->calculate_bill(
          iv_previous_reading = '12820'
          iv_current_reading  = '12000' ).
        cl_abap_unit_assert=>fail(
          msg = 'Expected cx_sy_illegal_argument' ).
      CATCH cx_sy_illegal_argument.
        cl_abap_unit_assert=>assert_true( abap_true ).
    ENDTRY.
  ENDMETHOD.
ENDCLASS.
