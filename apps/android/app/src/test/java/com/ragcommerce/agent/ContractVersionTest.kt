package com.ragcommerce.agent

import com.ragcommerce.agent.generated.CONTRACT_VERSION
import org.junit.Assert.assertEquals
import org.junit.Test

class ContractVersionTest {
    @Test
    fun generatedContractVersionMatchesBaseline() {
        assertEquals("0.2.0", CONTRACT_VERSION)
    }
}
