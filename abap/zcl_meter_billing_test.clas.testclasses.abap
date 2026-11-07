CLASS ltc_meter_billing DEFINITION
  FINAL
  FOR TESTING
  DURATION SHORT
  RISK LEVEL HARMLESS.

  PRIVATE SECTION.
    DATA cut TYPE REF TO zcl_meter_billing.

    METHODS setup.
    METHODS calculates_valid_bill FOR TESTING RAISING cx_sy_illegal_argument.
    METHODS rejects_decreasing_reading FOR TESTING.
    METHODS rejects_negative_previous FOR TESTING.
    METHODS rejects_negative_current FOR TESTING.
    METHODS bills_zero_consumption FOR TESTING RAISING cx_sy_illegal_argument.
    METHODS rounds_energy_half_up FOR TESTING RAISING cx_sy_illegal_argument.
    METHODS vat_uses_rounded_energy FOR TESTING RAISING cx_sy_illegal_argument.
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
      exp = CONV decfloat34( '370' ) ).

    cl_abap_unit_assert=>assert_equals(
      act = result-energy_amount
      exp = CONV decfloat34( '129.50' ) ).
    cl_abap_unit_assert=>assert_equals(
      act = result-basic_charge
      exp = CONV decfloat34( '12.00' ) ).
    cl_abap_unit_assert=>assert_equals(
      act = result-vat_amount
      exp = CONV decfloat34( '26.89' ) ).

    cl_abap_unit_assert=>assert_equals(
      act = result-total_amount
      exp = CONV decfloat34( '168.39' ) ).
    cl_abap_unit_assert=>assert_equals(
      act = result-status
      exp = CONV string( 'CREATED' ) ).
  ENDMETHOD.

  METHOD rejects_decreasing_reading.
    TRY.
        cut->calculate_bill(
          iv_previous_reading = '12820'
          iv_current_reading  = '12000' ).
        cl_abap_unit_assert=>fail(
          msg = 'Expected cx_sy_illegal_argument' ).
      CATCH cx_sy_illegal_argument.
        " Expected rejection; fail above catches a missing exception.
    ENDTRY.
  ENDMETHOD.

  METHOD rejects_negative_previous.
    DATA(validation) = cut->validate_reading(
      iv_previous_reading = '-1'
      iv_current_reading = '0' ).
    cl_abap_unit_assert=>assert_false( act = validation-valid ).
    cl_abap_unit_assert=>assert_equals(
      act = validation-message
      exp = CONV string( 'Readings cannot be negative' ) ).
    TRY.
        cut->calculate_bill(
          iv_previous_reading = '-1'
          iv_current_reading = '0' ).
        cl_abap_unit_assert=>fail( msg = 'Expected negative previous reading rejection' ).
      CATCH cx_sy_illegal_argument.
        " Expected.
    ENDTRY.
  ENDMETHOD.

  METHOD rejects_negative_current.
    DATA(validation) = cut->validate_reading(
      iv_previous_reading = '0'
      iv_current_reading = '-1' ).
    cl_abap_unit_assert=>assert_false( act = validation-valid ).
    cl_abap_unit_assert=>assert_equals(
      act = validation-message
      exp = CONV string( 'Readings cannot be negative' ) ).
    TRY.
        cut->calculate_bill(
          iv_previous_reading = '0'
          iv_current_reading = '-1' ).
        cl_abap_unit_assert=>fail( msg = 'Expected negative current reading rejection' ).
      CATCH cx_sy_illegal_argument.
        " Expected.
    ENDTRY.
  ENDMETHOD.

  METHOD bills_zero_consumption.
    DATA(result) = cut->calculate_bill(
      iv_previous_reading = '100'
      iv_current_reading = '100' ).
    cl_abap_unit_assert=>assert_equals(
      act = result-consumption_kwh exp = CONV decfloat34( '0' ) ).
    cl_abap_unit_assert=>assert_equals(
      act = result-energy_amount exp = CONV decfloat34( '0' ) ).
    cl_abap_unit_assert=>assert_equals(
      act = result-vat_amount exp = CONV decfloat34( '2.28' ) ).
    cl_abap_unit_assert=>assert_equals(
      act = result-total_amount exp = CONV decfloat34( '14.28' ) ).
  ENDMETHOD.

  METHOD rounds_energy_half_up.
    " 0.3 * 0.35 = 0.105: half-up gives 0.11, half-even would give 0.10.
    DATA(result) = cut->calculate_bill(
      iv_previous_reading = '100'
      iv_current_reading = '100.3' ).
    cl_abap_unit_assert=>assert_equals(
      act = result-energy_amount exp = CONV decfloat34( '0.11' ) ).
    cl_abap_unit_assert=>assert_equals(
      act = result-vat_amount exp = CONV decfloat34( '2.30' ) ).
    cl_abap_unit_assert=>assert_equals(
      act = result-total_amount exp = CONV decfloat34( '14.41' ) ).
  ENDMETHOD.

  METHOD vat_uses_rounded_energy.
    " VAT on 0.03 is 0.0057 -> 0.01; VAT on raw 0.025 would round to 0.
    DATA(result) = cut->calculate_bill(
      iv_previous_reading = '0'
      iv_current_reading = '1'
      iv_price_per_kwh = '0.025'
      iv_basic_charge = '0' ).
    cl_abap_unit_assert=>assert_equals(
      act = result-energy_amount exp = CONV decfloat34( '0.03' ) ).
    cl_abap_unit_assert=>assert_equals(
      act = result-vat_amount exp = CONV decfloat34( '0.01' ) ).
    cl_abap_unit_assert=>assert_equals(
      act = result-total_amount exp = CONV decfloat34( '0.04' ) ).
  ENDMETHOD.
ENDCLASS.
